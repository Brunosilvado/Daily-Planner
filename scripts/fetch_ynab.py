"""
YNAB fetcher.

Uses a YNAB Personal Access Token (generated once in YNAB under Account
Settings -> Developer Settings) stored as GitHub Secrets:
  YNAB_TOKEN       - the personal access token
  YNAB_BUDGET_ID   - which budget to read (the segment in the YNAB URL
                     right after app.ynab.com/, e.g. app.ynab.com/<this>/budget)

Until both are set, this returns None and the dashboard shows its honest
"YNAB isn't connected yet" state.

Also reads (optional, not a secret — a plain repo "Variable" works fine,
Settings -> Secrets and variables -> Actions -> Variables tab):
  YNAB_EXPECTED_MONTHLY_INCOME - what you typically expect to bring in
    this month, used only to flag if this month's budgeted amount runs
    ahead of that. Defaults to 5197.42 if not set. Update it there
    whenever your expected income changes — no code change needed.

Calendar month, CASH-basis (changed 2026-10-30 at Bruno's request):
  This used to show a rolling 30-day window using YNAB's own accrual
  convention (a credit card purchase counts as "spent" the day you swipe
  it; paying the card bill later was a "transfer," excluded entirely).
  That's the right way to track a BUDGET, but it quietly hid the thing
  Bruno actually wanted to see: "did my bank balance really grow or
  shrink this month" — because paying off last month's card bill is a
  real chunk of cash leaving checking, and under the old accrual view it
  never showed up as "spent" in the month it was actually paid.

  So this now tracks real cash movement, for the actual calendar month,
  using each account's TYPE (fetched once via /budgets/{id}/accounts):
    - checking/cash accounts are "where your spendable money lives."
      Only THESE accounts' transactions get counted at all.
    - A transfer from checking to a credit-card/line-of-credit account
      (i.e. paying the bill) counts as SPENT — that's the real cash
      leaving, in the month you actually paid it, which is the whole
      point of this change.
    - A transfer from checking to a savings account counts as SAVED,
      tracked separately from "spent" — it's still your money, just set
      aside, so it shouldn't look like it vanished. A transfer the other
      way (drawing savings back into checking) subtracts from "saved."
    - A transfer between two checking/cash accounts (reshuffling your
      own spendable money) counts as neither — it nets to zero either way.
    - Everything else (a plain purchase, a paycheck deposit) counts
      exactly as it looks: non-transfer money in is income, money out is
      spending.
  "This month" resets to $0 on the 1st on purpose now — that's what
  "the current month" means — so the first few days of a new month will
  look thin until transactions catch up; that's expected, not a bug.

Security notes:
  - YNAB's API doesn't offer a read-only scoped token — any Personal
    Access Token can technically read and write. This code only ever
    issues GET requests, so it can't change anything in your budget
    regardless of what the token could do. If this token is ever
    exposed, regenerate it in YNAB immediately (that instantly revokes
    the old one).
  - The token is only ever read from the environment (injected by GitHub
    Actions from the secret) and is never printed, logged, or written to
    data.json.
  - Scope stays cash-flow only: income, spent, net and a monthly budgeted
    vs. expected-income check. No account or card balances, and no
    individual transaction detail is ever written to data.json — per the
    project's privacy rule, that would need a further explicit ask.
  - One deliberate exception to "no account/category specifics," added by
    request: the NAME of any category that's over budget this month (and
    by how much), so the dashboard can actually warn "Groceries is $40
    over" rather than just a vague overall number. This is a bit more
    specific than everything else YNAB sends to this dashboard — still no
    transaction detail, but a real category name is now in data.json
    (see README.md's Security notes).
"""
import os
import sys
import datetime
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
import requests

API_BASE = "https://api.ynab.com/v1"
TIMEOUT_SECONDS = 15
DEFAULT_EXPECTED_MONTHLY_INCOME = 5197.42

# Account-type classification for the cash-basis calculation — see the
# module docstring's "Calendar month, CASH-basis" section for what each
# bucket means. Spelled out as sets (not a single dict) because YNAB has
# several account "type" strings and only a few matter here; anything not
# in any of these three sets (investmentAccount, mortgage, payPal, etc.)
# is simply left out of the cash-flow calculation entirely, same as it
# would be if transfers to/from it were excluded outright.
CHECKING_ACCOUNT_TYPES = {"checking", "cash"}
SAVINGS_ACCOUNT_TYPES = {"savings"}
CREDIT_ACCOUNT_TYPES = {"creditCard", "lineOfCredit"}


def _get(path, token):
    resp = requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["data"]


def _money_from_milli(milli):
    return round(milli / 1000, 2)


def _get_account_types(budget_id, token):
    """One call, cached by the caller for the whole run: {account_id:
    type_string} for every account in the budget, open or closed (a
    closed account can still own historical transactions this month's
    range might include). Safe to log only a count — see the print
    below — never account names, which YNAB account names very often
    are (e.g. "Bruno — Chase Checking")."""
    accounts = _get(f"/budgets/{budget_id}/accounts", token)["accounts"]
    by_id = {a["id"]: a.get("type") for a in accounts}
    print(f"[fetch_ynab] {len(by_id)} account(s) on this budget", file=sys.stderr)
    return by_id


def _cash_flow_for_range(budget_id, token, account_types, since_date, before_date):
    """Real cash-basis income/spent/saved for transactions dated
    `since_date` (inclusive) up to `before_date` (EXCLUSIVE) — pass
    tomorrow's date as before_date to mean "through today." See the
    module docstring's "Calendar month, CASH-basis" section for exactly
    what counts as what; this is that logic, mechanically. Only
    transactions that happened ON a checking/cash account are examined
    at all — a transaction that lives entirely on a credit card or
    savings account (the OTHER leg of a transfer counted below) is
    skipped here to avoid double-counting, since every transfer already
    shows up once on its checking-account leg."""
    transactions = _get(
        f"/budgets/{budget_id}/transactions?since_date={since_date}", token
    )["transactions"]

    income_milli = 0
    spent_milli = 0
    saved_milli = 0
    for t in transactions:
        if t.get("deleted"):
            continue
        if t["date"] >= before_date:
            continue  # since_date has no upper bound of its own; enforce one here
        if account_types.get(t.get("account_id")) not in CHECKING_ACCOUNT_TYPES:
            continue  # only look at the checking/cash side of the world
        amount = t.get("amount", 0)
        transfer_to = t.get("transfer_account_id")

        if not transfer_to:
            # An ordinary purchase or deposit — counts exactly as it looks.
            if amount > 0:
                income_milli += amount
            else:
                spent_milli += -amount
            continue

        other_type = account_types.get(transfer_to)
        if other_type in CREDIT_ACCOUNT_TYPES:
            # Paying a credit card bill FROM checking — this is the real
            # cash outflow this whole feature exists to capture. (A
            # payment never flows the other direction in practice, but
            # amount's sign is checked anyway rather than assumed.)
            if amount < 0:
                spent_milli += -amount
        elif other_type in SAVINGS_ACCOUNT_TYPES:
            # Money moved checking -> savings counts as saved (positive);
            # money pulled back the other way, savings -> checking,
            # subtracts from saved (you un-saved it, not "earned" it).
            saved_milli += -amount
        # else: transfer between two checking accounts, or to/from an
        # account type outside all three buckets (investments, mortgage,
        # etc.) — nets to zero / stays out of this view entirely, same
        # as the old rolling-window behavior for every transfer.

    return (
        _money_from_milli(income_milli),
        _money_from_milli(spent_milli),
        _money_from_milli(saved_milli),
    )


# Category groups to leave out of the overspending alert entirely — not
# because they're hidden from YNAB itself, but because a "negative
# balance" in either of these doesn't mean the same thing as ordinary
# overspending:
#   - "Credit Card Payments": YNAB auto-tracks what you owe here as you
#     spend on the card, so its balance moves for reasons that have
#     nothing to do with this month's budgeting decisions.
#   - "Internal Master Category": YNAB's own bookkeeping category (things
#     like "Uncategorized"), not a real spending category you budgeted.
EXCLUDED_CATEGORY_GROUPS = {"Credit Card Payments", "Internal Master Category"}


def _overspent_categories(budget_id, token, max_results=5):
    """Returns up to `max_results` categories that are over budget this
    month, worst first, as [{"category": name, "over": amount}, ...] —
    or [] once nothing is over.

    A category's "balance" going negative is YNAB's own definition of
    overspent: you've spent more in it this month than you'd budgeted,
    and (unless covered from somewhere else before the month closes)
    that shortfall rolls into eating next month's budget for the same
    category. Each entry's "category" name is real budget data (not a
    secret, but more specific than anything else this dashboard already
    shows), so this is deliberately scoped to the category *name* and
    *how far over* only — never which transactions caused it.

    Uses /budgets/{id}/categories (grouped by category_group, with each
    category's budgeted/activity/balance already reflecting the CURRENT
    budget month per YNAB's own API behavior) rather than the plain
    /months/current/categories list, specifically because this is the
    shape that actually tells us each category's group name — needed to
    apply EXCLUDED_CATEGORY_GROUPS above."""
    groups = _get(f"/budgets/{budget_id}/categories", token)["category_groups"]
    overspent = []
    for group in groups:
        if group.get("hidden") or group.get("deleted"):
            continue
        group_name = group.get("name") or ""
        if group_name in EXCLUDED_CATEGORY_GROUPS:
            continue
        for cat in group.get("categories", []):
            if cat.get("hidden") or cat.get("deleted"):
                continue
            balance_milli = cat.get("balance", 0)
            if balance_milli < 0:
                overspent.append({
                    "category": cat.get("name") or "(unnamed category)",
                    "over": _money_from_milli(-balance_milli),
                })
    overspent.sort(key=lambda c: c["over"], reverse=True)
    return overspent[:max_results]


def get_money_data():
    # .strip(): GitHub's secret textarea (or a clipboard manager) can pick
    # up a trailing newline/space on paste, which would otherwise silently
    # turn a correct token into an invalid Authorization header.
    token = (os.environ.get("YNAB_TOKEN") or "").strip()
    budget_id = (os.environ.get("YNAB_BUDGET_ID") or "").strip()
    if not token or not budget_id:
        return None

    # Safe to log: lengths only, never the values. Helps tell "wrong token"
    # apart from "token/id got truncated or merged by a copy-paste glitch"
    # without ever printing anything secret.
    print(f"[fetch_ynab] token length={len(token)}, budget_id length={len(budget_id)}",
          file=sys.stderr)

    # Central time, not the runner's own clock (always UTC on GitHub
    # Actions) — matters here specifically because "today" decides where
    # the this-month/last-month boundary falls; using UTC could flip to
    # the wrong month for several hours around midnight Central.
    today = datetime.datetime.now(CENTRAL).date()
    this_month_start = today.replace(day=1)
    last_month_end_day = this_month_start - datetime.timedelta(days=1)
    last_month_start = last_month_end_day.replace(day=1)
    tomorrow = today + datetime.timedelta(days=1)  # exclusive upper bound = "through today"

    months = _get(f"/budgets/{budget_id}/months", token)["months"]
    current_month_entry = next(
        (m for m in months if m["month"] == this_month_start.isoformat()), None
    )
    this_budgeted = _money_from_milli((current_month_entry or {}).get("budgeted", 0))

    this_month_label = today.strftime("%B")
    last_month_label = last_month_end_day.strftime("%B")

    account_types = _get_account_types(budget_id, token)
    this_income, this_spent, this_saved = _cash_flow_for_range(
        budget_id, token, account_types, this_month_start.isoformat(), tomorrow.isoformat()
    )
    last_income, last_spent, last_saved = _cash_flow_for_range(
        budget_id, token, account_types, last_month_start.isoformat(), this_month_start.isoformat()
    )

    expected_income_raw = os.environ.get("YNAB_EXPECTED_MONTHLY_INCOME")
    try:
        expected_income = (
            float(expected_income_raw) if expected_income_raw else DEFAULT_EXPECTED_MONTHLY_INCOME
        )
    except ValueError:
        expected_income = DEFAULT_EXPECTED_MONTHLY_INCOME

    now_central = datetime.datetime.now(CENTRAL).strftime(
        "%b %-d, %Y · %-I:%M %p Central"
    )

    over_budget = _overspent_categories(budget_id, token)
    # Safe to log: just a count. The category NAMES themselves do go into
    # data.json below (that's the whole point of the alert — "which
    # category" is the useful part), but never into this log, and never
    # any transaction detail behind the number.
    print(f"[fetch_ynab] {len(over_budget)} categor(y/ies) over budget this month",
          file=sys.stderr)

    return {
        "asOf": now_central,
        "thisMonth": {
            "label": this_month_label,
            "income": this_income,
            "spent": this_spent,
            "saved": this_saved,
            "budgeted": this_budgeted,
        },
        "lastMonth": {
            "label": last_month_label,
            "income": last_income,
            "spent": last_spent,
            "saved": last_saved,
        },
        "expectedMonthlyIncome": round(expected_income, 2),
        "overBudgetCategories": over_budget,
        "note": "From YNAB directly, cash-basis (includes credit card bill payments as spending "
                "when paid). Card purchases that don’t auto-sync into YNAB may understate spending.",
    }

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

Why "last 30 days" instead of "this calendar month":
  A calendar-month view resets to $0 on the 1st, so a credit card payment
  that lands on the 1st (covering purchases from the month that just
  ended) makes the brand-new month look artificially bad for a few days.
  A rolling 30-day window avoids that cliff — every day, it's simply "the
  last 30 days of real cash flow." Transfers between your own accounts
  (including paying off a tracked credit card) are excluded entirely, the
  same way YNAB's own reports exclude them, so money moving between your
  own accounts never counts as income or spending here.
  Note: this smooths the *presentation*; it can't retroactively fix a
  purchase that was entered as one lump payment-day transaction instead
  of being dated when it actually happened — that still needs fixing at
  the YNAB data-entry level to be fully accurate.

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
ROLLING_WINDOW_DAYS = 30


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


def _month_label(iso_date):
    d = datetime.date.fromisoformat(iso_date)
    return d.strftime("%B")


def _rolling_30_day_flow(budget_id, token, today):
    """Sums real income/spending over the trailing window, excluding any
    transaction that's a transfer between the user's own accounts (a
    credit card payment, a checking->savings move, etc.) — matching how
    YNAB's own category/month reports already treat transfers."""
    since = (today - datetime.timedelta(days=ROLLING_WINDOW_DAYS - 1)).isoformat()
    transactions = _get(
        f"/budgets/{budget_id}/transactions?since_date={since}", token
    )["transactions"]

    income_milli = 0
    spent_milli = 0
    for t in transactions:
        if t.get("deleted"):
            continue
        if t.get("transfer_account_id"):
            continue  # transfer between the user's own accounts — not real cash flow
        amount = t.get("amount", 0)
        if amount > 0:
            income_milli += amount
        else:
            spent_milli += -amount

    return _money_from_milli(income_milli), _money_from_milli(spent_milli)


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

    today = datetime.date.today()

    months = _get(f"/budgets/{budget_id}/months", token)["months"]
    past_or_current = [
        m for m in months if datetime.date.fromisoformat(m["month"]) <= today
    ]
    past_or_current.sort(key=lambda m: m["month"], reverse=True)
    if not past_or_current:
        return None

    current = past_or_current[0]
    previous = past_or_current[1] if len(past_or_current) > 1 else None

    def label_and_amounts(entry):
        if entry is None:
            return "", 0, 0
        return (
            _month_label(entry["month"]),
            _money_from_milli(entry.get("income", 0)),
            _money_from_milli(-entry.get("activity", 0)),  # activity is negative for spending
        )

    last_label, last_income, last_spent = label_and_amounts(previous)
    this_month_label = _month_label(current["month"])
    this_budgeted = _money_from_milli(current.get("budgeted", 0))

    last30_income, last30_spent = _rolling_30_day_flow(budget_id, token, today)

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
        "last30": {"income": last30_income, "spent": last30_spent},
        "thisMonth": {"label": this_month_label, "budgeted": this_budgeted},
        "lastMonth": {"label": last_label, "income": last_income, "spent": last_spent},
        "expectedMonthlyIncome": round(expected_income, 2),
        "overBudgetCategories": over_budget,
        "note": "From YNAB directly. Card purchases that don’t auto-sync into YNAB may understate spending.",
    }

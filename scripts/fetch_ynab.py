"""
YNAB fetcher.

Uses a YNAB Personal Access Token (generated once in YNAB under Account
Settings -> Developer Settings) stored as GitHub Secrets:
  YNAB_TOKEN       - the personal access token
  YNAB_BUDGET_ID   - which budget to read (the segment in the YNAB URL
                     right after app.ynab.com/, e.g. app.ynab.com/<this>/budget)

Until both are set, this returns None and the dashboard shows its honest
"YNAB isn't connected yet" state.

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
  - Scope stays cash-flow only: income, spent, net and Ready to Assign.
    No account or card balances — per the project's privacy rule, that
    would need a further explicit ask.
"""
import os
import sys
import datetime
import requests

API_BASE = "https://api.ynab.com/v1"
TIMEOUT_SECONDS = 15


def _get(path, token):
    resp = requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["data"]


def _month_label(iso_date):
    d = datetime.date.fromisoformat(iso_date)
    return d.strftime("%B")


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

    months = _get(f"/budgets/{budget_id}/months", token)["months"]
    # YNAB returns months newest-first, future months included; keep only
    # months that have actually started (budgeted <= 0 means unused future
    # month in YNAB's convention isn't reliable, so filter by date instead).
    today = datetime.date.today()
    past_or_current = [
        m for m in months if datetime.date.fromisoformat(m["month"]) <= today
    ]
    past_or_current.sort(key=lambda m: m["month"], reverse=True)

    if not past_or_current:
        return None

    current = past_or_current[0]
    previous = past_or_current[1] if len(past_or_current) > 1 else None

    def money_from_milli(milli):
        return round(milli / 1000, 2)

    this_month_started = current["month"] == today.replace(day=1).isoformat()
    last_month_entry = current if not this_month_started else previous

    def label_and_amounts(entry):
        if entry is None:
            return "", 0, 0
        return (
            _month_label(entry["month"]),
            money_from_milli(entry.get("income", 0)),
            money_from_milli(-entry.get("activity", 0)),  # activity is negative for spending
        )

    last_label, last_income, last_spent = label_and_amounts(last_month_entry)
    this_label, this_income, this_spent = (
        label_and_amounts(current) if this_month_started else ("", 0, 0)
    )

    now_central = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%b %-d, %Y · %-I:%M %p UTC"
    )

    return {
        "asOf": now_central,
        "lastMonth": {"label": last_label, "income": last_income, "spent": last_spent},
        "thisMonth": {"label": this_label, "income": this_income, "spent": this_spent},
        "readyToAssign": money_from_milli(current.get("to_be_budgeted", 0)),
        "note": "From YNAB directly. Card purchases that don’t auto-sync into YNAB may understate spending.",
    }

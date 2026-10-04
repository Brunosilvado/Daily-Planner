"""
YNAB fetcher — Phase 2.

Uses a YNAB Personal Access Token (the simplest of the three — no OAuth
flow, generated once in YNAB under Account Settings -> Developer Settings)
stored as the GitHub Secrets below.

Required secrets (not yet configured):
  YNAB_TOKEN
  YNAB_BUDGET_ID

Until those are set, this returns None and the dashboard shows its honest
"YNAB isn't connected yet" state. Scope stays cash-flow only: income,
spent, net and Ready to Assign. No account or card balances — per the
project's privacy rule, that would need a further explicit ask.
"""
import os


def get_money_data():
    if not os.environ.get("YNAB_TOKEN"):
        return None

    # TODO (Phase 2): call https://api.ynab.com/v1/budgets/{budget_id}/months
    # for the last two months and the budget's "to_be_budgeted" figure, then build:
    #   {"asOf": "<human readable Central time>",
    #    "lastMonth": {"label": "...", "income": 0, "spent": 0},
    #    "thisMonth": {"label": "...", "income": 0, "spent": 0},
    #    "readyToAssign": 0,
    #    "note": "From YNAB directly."}
    return None

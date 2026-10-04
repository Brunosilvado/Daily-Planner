"""
Assembles data.json content for the dashboard.

Each get_*() function below checks for the secrets/env vars it needs and
either returns real, freshly-fetched data or an honest "not connected yet"
fallback that matches the dashboard's own default state (see site/app.js).
Nothing here is ever committed to git — this only runs inside a GitHub
Actions job and its output goes straight into the Pages deployment
artifact, never into the repository.

Phase 2 TODO (once secrets are configured):
  - fetch_calendar.get_calendar_data(): Google Calendar via a refresh token
    (GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET / GOOGLE_OAUTH_REFRESH_TOKEN)
  - fetch_ynab.get_money_data(): YNAB Personal Access Token (YNAB_TOKEN, YNAB_BUDGET_ID)
  - fetch_todo.get_tasks_data(): Microsoft Graph device-code refresh token
    (MS_GRAPH_CLIENT_ID / MS_GRAPH_REFRESH_TOKEN)
"""
import os
import datetime

from fetch_calendar import get_calendar_data
from fetch_ynab import get_money_data
from fetch_todo import get_tasks_data


def build():
    now = datetime.datetime.now(datetime.timezone.utc)

    live_data = get_calendar_data() or {
        "calendarConnected": False,
        "todoConnected": False,
        "asOf": "",
        "items": {},
    }

    money = get_money_data() or {
        "asOf": "",
        "lastMonth": {"label": "", "income": 0, "spent": 0},
        "thisMonth": {"label": "", "income": 0, "spent": 0},
        "readyToAssign": 0,
        "note": "YNAB isn't connected yet.",
    }

    tasks = get_tasks_data() or {
        "asOf": "",
        "groups": [],
    }
    # todoConnected tracks separately from calendarConnected inside liveData
    live_data["todoConnected"] = bool(os.environ.get("MS_GRAPH_REFRESH_TOKEN"))

    return {
        "generatedAt": now.isoformat(),
        "liveData": live_data,
        "money": money,
        "tasks": tasks,
    }

"""
Assembles data.json content for the dashboard.

Each get_*() function below checks for the secrets/env vars it needs and
either returns real, freshly-fetched data or an honest "not connected yet"
fallback that matches the dashboard's own default state (see site/app.js).
Nothing here is ever committed to git — this only runs inside a GitHub
Actions job and its output goes straight into the Pages deployment
artifact, never into the repository.

Security notes:
  - Each source is isolated in its own try/except below. If YNAB's API is
    down, or a token expired, that failure can't take the Calendar or
    To Do sections down with it — each section just falls back to its own
    honest "not connected" state.
  - Errors are logged with only their type and a short message, never with
    exception args/response bodies that could echo back a token or other
    sensitive value. Nothing here ever logs a secret.
  - Every fetcher only ever makes read (GET) calls to these APIs — see the
    fetch_*.py files. Least privilege: this pipeline can't change or
    delete anything in your Calendar, YNAB or To Do accounts even if a
    token were somehow misused.
"""
import os
import sys
import datetime

from fetch_calendar import get_calendar_data
from fetch_ynab import get_money_data
from fetch_todo import get_tasks_data

DEFAULT_LIVE_DATA = {
    "calendarConnected": False,
    "todoConnected": False,
    "asOf": "",
    "items": {},
}

DEFAULT_MONEY = {
    "asOf": "",
    "last30": {"income": 0, "spent": 0},
    "thisMonth": {"label": "", "budgeted": 0},
    "lastMonth": {"label": "", "income": 0, "spent": 0},
    "expectedMonthlyIncome": 0,
    "note": "YNAB isn't connected yet.",
}

DEFAULT_TASKS = {
    "asOf": "",
    "groups": [],
}


def _safe_fetch(label, fn, default):
    """Run one source's fetcher; on any failure, log a short, secret-free
    message and fall back to that source's honest 'not connected' default
    rather than letting one source's outage break the whole dashboard."""
    try:
        result = fn()
        return result if result is not None else dict(default)
    except Exception as exc:  # noqa: BLE001 - deliberate: isolate every source
        detail = ""
        resp = getattr(exc, "response", None)
        if resp is not None:
            # Safe to log: HTTP status + reason only, never headers/body,
            # so a token can never end up in the Actions log.
            detail = f", HTTP {resp.status_code} {resp.reason}"
        print(f"[build_data] {label} fetch failed ({type(exc).__name__}{detail}) — "
              f"falling back to 'not connected'.", file=sys.stderr)
        return dict(default)


def build():
    """Called once per run by build_site.py. Fetches all three sources
    (each isolated by _safe_fetch above, so one failing doesn't take the
    others down) and returns the single dict that gets written to
    data.json verbatim — site/app.js reads exactly this shape back out.
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    live_data = _safe_fetch("calendar", get_calendar_data, DEFAULT_LIVE_DATA)
    money = _safe_fetch("ynab", get_money_data, DEFAULT_MONEY)
    tasks = _safe_fetch("todo", get_tasks_data, DEFAULT_TASKS)

    # todoConnected lives inside liveData (alongside calendarConnected)
    # purely for historical reasons — it's read by app.js wherever a
    # Calendar-card note needs to mention To Do's status too. Worth
    # knowing if you're debugging it: unlike calendarConnected (which
    # fetch_calendar.py only sets True after an actual successful fetch),
    # this is just "is the secret present at all" — it doesn't by itself
    # guarantee the most recent fetch_todo.py call succeeded. In
    # practice this doesn't cause wrong-looking output, because
    # site/app.js's Tasks and "Due today" cards separately check
    # `tasks.groups.length`, which DOES reflect a real, successful fetch
    # (DEFAULT_TASKS above is always an empty list on any failure) — but
    # it's a subtlety worth knowing if this ever needs changing.
    live_data["todoConnected"] = bool(os.environ.get("MS_GRAPH_REFRESH_TOKEN"))

    return {
        "generatedAt": now.isoformat(),  # read by app.js's renderFooter()
        "liveData": live_data,
        "money": money,
        "tasks": tasks,
    }

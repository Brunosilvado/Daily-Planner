"""
Microsoft To Do fetcher.

Uses a refresh token minted once via Microsoft's device-code sign-in
(public client, delegated "Tasks.Read" + "offline_access" scopes), stored
as GitHub Secrets:
  MS_GRAPH_CLIENT_ID       - the Azure app registration's Application ID
  MS_GRAPH_REFRESH_TOKEN   - from the one-time device-code consent run

Until both are set, this returns None and the dashboard shows its honest
"To Do isn't connected yet" state.

What's shown: open (non-completed) tasks from every To Do list EXCEPT the
two standing-routine checklists ("Household Routines", "Trading
Development") — those are recurring routines you already see elsewhere on
the dashboard, so repeating them here would just be noise. Everything else
that's still open shows up, with its due date and whether it's overdue.

Security notes:
  - Requests only the delegated "Tasks.Read" scope (read-only) plus
    "offline_access" (needed to get a refresh token at all) — this code
    cannot create, edit, complete, or delete anything in your To Do lists
    even if a token were somehow misused.
  - Only ever makes GET calls to Microsoft Graph.
  - The client ID and refresh token are only ever read from the
    environment and never printed, logged, or written to data.json.
  - A note on refresh tokens: Microsoft sometimes rotates the refresh
    token on use and the previous one may stop working. This pipeline
    doesn't attempt to auto-update the stored secret with a new one (that
    would need a separate, more broadly-scoped GitHub token). If To Do
    ever shows "not connected" again after working fine for a while, the
    fix is just re-running the local consent script once to mint a fresh
    token.
"""
import datetime
import os
import sys

import requests

TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPE = "https://graph.microsoft.com/Tasks.Read offline_access"
TIMEOUT_SECONDS = 15

# Standing routine checklists shown elsewhere on the dashboard already —
# excluded here so they don't show up twice.
EXCLUDED_LISTS = {"Household Routines", "Trading Development"}

try:
    from zoneinfo import ZoneInfo
    CENTRAL = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover - defensive only
    CENTRAL = None


def _log_if_error(resp, label):
    """Safe to log: only a short machine-readable error code — Microsoft's
    AAD token endpoint uses a flat {"error": "invalid_grant", ...} shape,
    Graph API uses a nested {"error": {"code": "BadRequest", ...}} shape —
    never error_description/message, which can echo back contextual
    detail, and never the request or response body otherwise."""
    if resp.ok:
        return
    try:
        body = resp.json()
        err = body.get("error")
        code = err.get("code") if isinstance(err, dict) else err
        code = code or "(no error code in response)"
    except ValueError:
        code = "(non-JSON response)"
    print(f"[fetch_todo] {label} rejected: {code}", file=sys.stderr)


def _get_access_token(client_id, refresh_token):
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": SCOPE,
        },
        timeout=TIMEOUT_SECONDS,
    )
    _log_if_error(resp, "token exchange")
    resp.raise_for_status()
    return resp.json()["access_token"]


def _fetch_lists(access_token):
    # No query params here: Microsoft's To Do API has limited/inconsistent
    # support for OData options like $select on this endpoint and returns
    # a plain 400 "invalidRequest" rather than ignoring what it doesn't
    # support — simplest fix is to just fetch the full (small) objects and
    # read the two fields we need from them.
    resp = requests.get(
        f"{GRAPH_BASE}/me/todo/lists",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=TIMEOUT_SECONDS,
    )
    _log_if_error(resp, "list-lists call")
    resp.raise_for_status()
    return resp.json().get("value", [])


def _fetch_open_tasks(access_token, list_id):
    # Dropped $select here too, for the same reason as _fetch_lists above
    # — keeping only $filter/$top, which are the well-supported options
    # on this subresource.
    resp = requests.get(
        f"{GRAPH_BASE}/me/todo/lists/{list_id}/tasks",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "$filter": "status ne 'completed'",
            "$top": 50,
        },
        timeout=TIMEOUT_SECONDS,
    )
    _log_if_error(resp, "list-tasks call")
    resp.raise_for_status()
    return resp.json().get("value", [])


def _due_date(task, today):
    """Returns (label, iso_date, overdue) for a task's due date, or
    (None, None, False) if it has none. Graph returns dueDateTime as a
    naive date/time in the given timeZone (often UTC) — since To Do due
    dates are really just calendar dates (no meaningful time-of-day), we
    read the date part only rather than converting clock time across
    zones. iso_date (plain "YYYY-MM-DD") is for the dashboard's own code
    to compare dates against exactly — label is for display only and
    deliberately not machine-parseable (e.g. "Oct 5"), so both are sent."""
    due_raw = task.get("dueDateTime")
    if not due_raw or not due_raw.get("dateTime"):
        return None, None, False
    try:
        due_date = datetime.date.fromisoformat(due_raw["dateTime"][:10])
    except ValueError:
        return None, None, False
    overdue = due_date < today
    return due_date.strftime("%b %-d"), due_date.isoformat(), overdue


def get_tasks_data():
    # .strip() alone only trims the two ends. A refresh token wraps across
    # several lines in a terminal, and if that got selected/copied as
    # multiple lines (rather than one unwrapped line), an embedded newline
    # or space would land in the middle of the secret and invalidate it
    # outright — so this strips ALL whitespace, not just leading/trailing.
    raw_client_id = os.environ.get("MS_GRAPH_CLIENT_ID") or ""
    raw_refresh_token = os.environ.get("MS_GRAPH_REFRESH_TOKEN") or ""
    client_id = "".join(raw_client_id.split())
    refresh_token = "".join(raw_refresh_token.split())
    if not (client_id and refresh_token and CENTRAL):
        return None

    # Safe to log: lengths and counts only, never the values or task text.
    # If the "raw" and cleaned lengths differ, the secret had embedded
    # whitespace/newlines — a strong sign of a multi-line copy-paste.
    print(f"[fetch_todo] client_id length={len(client_id)} (raw {len(raw_client_id.strip())}), "
          f"refresh_token length={len(refresh_token)} (raw {len(raw_refresh_token.strip())})",
          file=sys.stderr)

    today = datetime.datetime.now(CENTRAL).date()
    access_token = _get_access_token(client_id, refresh_token)

    all_lists = _fetch_lists(access_token)
    excluded_count = sum(1 for l in all_lists if (l.get("displayName") or "") in EXCLUDED_LISTS)
    # Counts only — never list names or task text in a public repo's logs.
    print(f"[fetch_todo] found {len(all_lists)} list(s), "
          f"{excluded_count} excluded as standing routines", file=sys.stderr)

    groups = []
    for todo_list in all_lists:
        name = todo_list.get("displayName") or "List"
        if name in EXCLUDED_LISTS:
            continue
        list_id = todo_list.get("id")
        if not list_id:
            continue
        open_tasks = _fetch_open_tasks(access_token, list_id)
        if not open_tasks:
            continue

        items = []
        for task in open_tasks:
            due_label, due_iso, overdue = _due_date(task, today)
            items.append({
                "text": task.get("title") or "(untitled)",
                "due": due_label,
                "dueISO": due_iso,
                "overdue": overdue,
            })
        # Overdue first, then by presence of a due date, keeping Graph's
        # own ordering within each group otherwise.
        items.sort(key=lambda it: (not it["overdue"], it["due"] is None))
        groups.append({"list": name, "items": items})

    now_label = datetime.datetime.now(CENTRAL).strftime("%b %-d, %Y · %-I:%M %p Central")
    print(f"[fetch_todo] returning {len(groups)} group(s) with open tasks",
          file=sys.stderr)

    return {
        "asOf": now_label,
        "groups": groups,
    }

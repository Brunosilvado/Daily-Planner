"""
Google Calendar fetcher.

Uses a refresh token minted once via Google's OAuth consent screen
("offline access", read-only Calendar scope), stored as GitHub Secrets:
  GOOGLE_OAUTH_CLIENT_ID
  GOOGLE_OAUTH_CLIENT_SECRET
  GOOGLE_OAUTH_REFRESH_TOKEN
  GOOGLE_CALENDAR_IDS  - a JSON array of {"id": "...", "label": "..."},
                         one per calendar to check. Kept out of the public
                         repo entirely (a calendar id can be an email
                         address, e.g. a primary calendar's id usually is
                         the account's own email) — this only ever exists
                         as an encrypted secret, injected as an env var at
                         job run time.

Until all are set, this returns None and the dashboard shows its honest
"Calendar isn't connected yet" state.

Security notes:
  - Requests only the read-only Calendar scope
    (https://www.googleapis.com/auth/calendar.readonly) — this code
    cannot create, edit, or delete anything on your calendars even if a
    token were somehow misused.
  - Only ever makes GET calls to the Calendar API.
  - The client secret and refresh token are only ever read from the
    environment and never printed, logged, or written to data.json.
  - Only fetches events for today and tomorrow (Central time) — nothing
    further out, nothing further back.
"""
import datetime
import json
import os

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL_TMPL = "https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
TIMEOUT_SECONDS = 15

try:
    from zoneinfo import ZoneInfo
    CENTRAL = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover - defensive only
    CENTRAL = None


def _get_access_token(client_id, client_secret, refresh_token):
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _fetch_events(access_token, cal_id, time_min, time_max):
    resp = requests.get(
        EVENTS_URL_TMPL.format(cal_id=cal_id),
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 50,
        },
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def _format_range(start, end, all_day):
    if all_day:
        return None  # no time prefix for all-day items
    start_period, end_period = start.strftime("%p"), end.strftime("%p")
    start_s = start.strftime("%-I:%M") if start_period == end_period else start.strftime("%-I:%M %p")
    end_s = end.strftime("%-I:%M %p")
    return f"{start_s}–{end_s}"


def get_calendar_data():
    client_id = (os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    refresh_token = (os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN") or "").strip()
    calendars_raw = (os.environ.get("GOOGLE_CALENDAR_IDS") or "").strip()
    if not (client_id and client_secret and refresh_token and calendars_raw and CENTRAL):
        return None

    calendars = json.loads(calendars_raw)  # [{"id": "...", "label": "..."}, ...]
    if not calendars:
        return None

    access_token = _get_access_token(client_id, client_secret, refresh_token)

    now_central = datetime.datetime.now(CENTRAL)
    today_start = now_central.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = today_start + datetime.timedelta(days=2)  # covers today + tomorrow

    items = {
        today_start.date().isoformat(): [],
        (today_start + datetime.timedelta(days=1)).date().isoformat(): [],
    }

    for cal in calendars:
        cal_id = cal.get("id")
        label = cal.get("label") or "Calendar"
        if not cal_id:
            continue
        events = _fetch_events(access_token, cal_id, today_start, tomorrow_end)
        for event in events:
            if event.get("status") == "cancelled":
                continue
            start_raw = event.get("start", {})
            end_raw = event.get("end", {})
            all_day = "date" in start_raw
            if all_day:
                event_date = start_raw["date"]
                time_range = None
            else:
                start_dt = datetime.datetime.fromisoformat(start_raw["dateTime"]).astimezone(CENTRAL)
                end_dt = datetime.datetime.fromisoformat(end_raw["dateTime"]).astimezone(CENTRAL)
                event_date = start_dt.date().isoformat()
                time_range = _format_range(start_dt, end_dt, all_day)
            if event_date not in items:
                continue  # outside today/tomorrow (shouldn't happen given timeMin/timeMax, but safe)
            summary = event.get("summary", "(no title)")
            text = f"{label} — {summary}"
            items[event_date].append({"time": time_range, "sortKey": time_range or "", "text": text})

    for date_key in items:
        items[date_key].sort(key=lambda it: it["sortKey"])
        for it in items[date_key]:
            del it["sortKey"]

    now_label = now_central.strftime("%b %-d, %Y · %-I:%M %p Central")

    return {
        "calendarConnected": True,
        "todoConnected": False,  # build_data.py overwrites this from its own check
        "asOf": now_label,
        "items": items,
    }

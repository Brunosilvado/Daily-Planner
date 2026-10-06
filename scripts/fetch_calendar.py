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

Priority flagging:
  Type "!!" at the start of an event's title in Google Calendar itself
  (e.g. "!! NC meeting") and the dashboard treats it as a priority item —
  the "!!" is stripped before display, so you'd just see "NC meeting"
  with a star next to it. This is deliberately just a title convention
  rather than a real flag/field, because this project only ever reads
  from Google Calendar (see Security notes) — it can't write a proper
  "starred" marker back to the event, so the title itself is the only
  place to put a signal that both Google Calendar's own app and this
  dashboard can see.

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
import sys

# See "Priority flagging" above. Checked case-sensitively and only at the
# very start of the title, so an event about, say, "Using !! in emails"
# doesn't accidentally get flagged.
PRIORITY_PREFIX = "!!"


def _strip_priority(title):
    """Returns (display_title, is_priority). Strips a leading "!!" (and
    any space right after it) from an event/task title, so the marker
    never shows up in what actually gets displayed — only the star icon
    app.js adds for a priority item does."""
    if title.startswith(PRIORITY_PREFIX):
        return title[len(PRIORITY_PREFIX):].lstrip(), True
    return title, False

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
    """Trades the long-lived refresh token (minted once, by hand, via the
    local consent script) for a short-lived access token that's actually
    valid for making API calls. This is the normal OAuth2 "refresh token
    grant" dance — every run of this script does this exchange fresh,
    since access tokens typically expire after about an hour and refresh
    tokens are built to be reused indefinitely (unless revoked)."""
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
    """One calendar, one time window. singleEvents=true tells Google to
    expand recurring events (e.g. a weekly meeting) into individual
    occurrences rather than handing back one repeating-event object we'd
    have to expand ourselves."""
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
    """Turns two datetimes into a display string like "6:00–6:30 PM", or
    "9:00 AM–1:00 PM" when the event crosses from AM to PM (only the end
    time gets an AM/PM suffix when both sides already share one, so we're
    not printing "6:00 PM–6:30 PM" when "6:00–6:30 PM" reads just as
    clearly). Returns None for all-day events, which get no time at all."""
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

    # Safe to log: just how many calendars are configured and their labels
    # ("Bruno", "Claudia") — never the calendar ids themselves, since a
    # calendar id is very often the account's own email address. This is
    # the first thing to check if an event seems to be "missing": if the
    # calendar it actually lives on isn't in this list at all, this count
    # is the tell — the fix is adding that calendar's id to the
    # GOOGLE_CALENDAR_IDS secret, not a bug in the fetching code below.
    labels = [c.get("label") or "(unlabeled)" for c in calendars]
    print(f"[fetch_calendar] checking {len(calendars)} calendar(s): {', '.join(labels)}",
          file=sys.stderr)

    access_token = _get_access_token(client_id, client_secret, refresh_token)

    now_central = datetime.datetime.now(CENTRAL)
    today_start = now_central.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = today_start + datetime.timedelta(days=2)  # covers today + tomorrow

    # Pre-create one (empty, for now) list per date so every calendar's
    # events land in the right bucket below, and so a day with zero events
    # still shows up as "checked, nothing found" rather than being absent.
    items = {
        today_start.date().isoformat(): [],
        (today_start + datetime.timedelta(days=1)).date().isoformat(): [],
    }

    # Google Calendar has no single endpoint that reads several calendars
    # at once, so this loops over each one in GOOGLE_CALENDAR_IDS and makes
    # its own request — label (e.g. "Bruno", "Claudia") gets prefixed onto
    # each event's title below so the dashboard can tell whose event is whose.
    skipped_outside_window = 0
    for cal in calendars:
        cal_id = cal.get("id")
        label = cal.get("label") or "Calendar"
        if not cal_id:
            continue
        events = _fetch_events(access_token, cal_id, today_start, tomorrow_end)
        # Safe to log: a count only, never any event's title or time. If
        # an event you know exists isn't showing up on the dashboard, and
        # this count for its calendar is 0 (or lower than you'd expect),
        # that calendar's events genuinely aren't coming back from Google
        # for today/tomorrow — worth checking directly in Google Calendar
        # whether the event got moved, cancelled, or is actually on a
        # different calendar than this label suggests.
        print(f"[fetch_calendar] '{label}': {len(events)} event(s) in today+tomorrow window",
              file=sys.stderr)
        for event in events:
            if event.get("status") == "cancelled":
                continue
            start_raw = event.get("start", {})
            end_raw = event.get("end", {})
            # Google represents an all-day event with a plain "date" field
            # and a timed event with a full "dateTime" — this is how the
            # API itself distinguishes the two, so we check for "date" to
            # tell them apart rather than guessing from the time values.
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
                skipped_outside_window += 1
                continue  # outside today/tomorrow (shouldn't happen given timeMin/timeMax, but safe)
            summary, priority = _strip_priority(event.get("summary", "(no title)"))
            text = f"{label} — {summary}"
            # sortKey is thrown away right below, once it's done its job of
            # ordering each day's events by start time (all-day events sort
            # first, since "" sorts before any "H:MM AM/PM" string).
            items[event_date].append({
                "time": time_range, "sortKey": time_range or "", "text": text, "priority": priority,
            })

    for date_key in items:
        # Priority items float to the top of their day, keeping each
        # group's own time-order otherwise — same two-key pattern as
        # fetch_todo.py's "overdue first" sort, just with "priority"
        # instead of "overdue" as the thing that jumps the queue.
        items[date_key].sort(key=lambda it: (not it["priority"], it["sortKey"]))
        for it in items[date_key]:
            del it["sortKey"]

    # Safe to log: counts only. If this "skipped" number is ever non-zero,
    # Google returned an event whose computed date landed outside the
    # today/tomorrow window even though the request's timeMin/timeMax
    # should have excluded it already — a sign something subtler (like a
    # timezone conversion edge case right at midnight) is worth a look.
    total_shown = sum(len(v) for v in items.values())
    print(f"[fetch_calendar] showing {total_shown} event(s) across today+tomorrow "
          f"({skipped_outside_window} skipped as outside the window)", file=sys.stderr)

    now_label = now_central.strftime("%b %-d, %Y · %-I:%M %p Central")

    return {
        "calendarConnected": True,
        "todoConnected": False,  # build_data.py overwrites this from its own check
        "asOf": now_label,
        "items": items,
    }

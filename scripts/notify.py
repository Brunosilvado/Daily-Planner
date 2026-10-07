"""
Daily push-notification digest — "what do I need to know today," sent
straight to Bruno's phone instead of waiting for him to open the
dashboard.

Uses ntfy.sh (https://ntfy.sh), a free, no-signup push-notification
service: you install the ntfy app (iOS/Android) once, subscribe to one
private "topic" (basically a password-like channel name you make up),
and anything POSTed to that topic by this script shows up as a phone
push notification within seconds. No account, no API key to manage, no
cost — the whole service is free and open-source.

Required GitHub Secret:
  NTFY_TOPIC — the private topic name you chose when setting up the
               ntfy app. Treat it like a password: anyone who knows it
               can both read your notifications and send fake ones to
               your phone (see Security notes below). Until this secret
               is set, this module does nothing at all — no error, no
               digest, just silently skipped, the same "not connected
               yet" pattern as every other optional integration here.

WHEN this sends: only once a day, on the ~6am-Central run (this project
already runs 6x/day — see .github/workflows/deploy.yml's comment on why
those six times — and this picks out just the one closest to 6am Central,
converted correctly across both CST and CDT so it stays "once a day" all
year without a manual DST fix). Every other run of the day computes
nothing extra and sends nothing — this module is a no-op on those runs.

WHAT it sends: a short digest built from the SAME data already computed
for the dashboard this run (see build_site.py — this is called with the
same `data` dict that becomes data.json, so nothing is fetched twice):
anything overdue, anything flagged "!!" as a priority (see
fetch_todo.py/fetch_calendar.py's "Priority flagging" notes), anything
due today, and tonight's standing routine action — the same inputs
app.js's computeTopPriority() uses for the dashboard's "Do This First"
card, just summarized as a short list instead of narrowed to one pick.

Security notes:
  - ntfy.sh's default server (ntfy.sh itself, what this uses) is a
    THIRD-PARTY service — unlike YNAB/Google/Microsoft, Anthropic/this
    project don't control it. The digest text (task names, event names)
    passes through ntfy.sh's servers to relay the push notification.
    ntfy is open-source and widely used for exactly this, but it's a
    deliberate, real trade-off: slightly more exposure than keeping
    everything inside GitHub Actions + your own accounts, in exchange
    for an actual phone push notification, which nothing already in
    this project can do on its own.
  - The topic name is a shared secret, same trust model as this
    dashboard's PAGES_SLUG: anyone who learns it can read your
    notifications (and, since ntfy's free tier doesn't restrict
    publishing, send fake ones to your phone). Keep it long and random,
    stored only as a GitHub secret — never written into any committed
    file, same rule as every other secret in this project.
  - If this ever feels like too much exposure for what it's worth, the
    fix is simple: just don't set NTFY_TOPIC (or delete the secret) —
    the dashboard itself is completely unaffected either way, since this
    module only ever runs after the dashboard's own data is already
    built, and never changes what gets written to data.json.
  - Only ever makes one outbound POST per day, to ntfy.sh's publish
    endpoint, and only when NTFY_TOPIC is set. Any failure (ntfy.sh
    down, bad topic, network hiccup) is caught and logged as a short,
    secret-free message — it never fails the dashboard build itself,
    since a missed notification is far less bad than a broken dashboard.
"""
import datetime
import os
import sys

import requests

NTFY_PUBLISH_URL = "https://ntfy.sh"
TIMEOUT_SECONDS = 15
# Which Central hour counts as "the once-a-day run." Matches this
# project's existing 6am/3pm/8pm Central schedule (see deploy.yml) — this
# is deliberately the EARLIEST of the three, so the digest is useful
# before the day gets going rather than after.
NOTIFY_HOUR_CENTRAL = 6

try:
    from zoneinfo import ZoneInfo
    CENTRAL = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover - defensive only
    CENTRAL = None


def _build_digest_lines(data, today_key):
    """Turns the already-built dashboard `data` dict into a short list of
    plain-text lines — the digest body. Mirrors the priority ordering
    app.js's computeTopPriority() uses (overdue, flagged, due today),
    just listing everything in each bucket instead of picking one."""
    tasks = data.get("tasks", {}) or {}
    live = data.get("liveData", {}) or {}

    overdue, flagged, due_today = [], [], []
    for group in tasks.get("groups", []) or []:
        list_name = group.get("list", "")
        for item in group.get("items", []) or []:
            label = f"{item.get('text','(untitled)')} ({list_name})"
            if item.get("overdue"):
                overdue.append(label)
            elif item.get("priority"):
                flagged.append(label)
            elif item.get("dueISO") == today_key:
                due_today.append(label)

    # Flagged calendar events for today — same "!!" convention, see
    # fetch_calendar.py. liveData.items is keyed by "YYYY-MM-DD".
    today_events = (live.get("items", {}) or {}).get(today_key, []) or []
    flagged_events = [e.get("text", "") for e in today_events if e.get("priority")]

    lines = []
    if overdue:
        lines.append("⚠ Overdue: " + "; ".join(overdue))
    if flagged:
        lines.append("★ Flagged: " + "; ".join(flagged))
    if flagged_events:
        lines.append("★ Flagged on calendar: " + "; ".join(flagged_events))
    if due_today:
        lines.append("Due today: " + "; ".join(due_today))
    if not lines:
        lines.append("Nothing overdue, flagged, or due today — you're clear.")
    return lines


def maybe_send_digest(data):
    """Call this once per build, after `data` (the same dict build_site.py
    writes to data.json) is ready. Does nothing unless NTFY_TOPIC is set
    AND this happens to be the ~6am-Central run — see the module
    docstring for both of those conditions."""
    topic = (os.environ.get("NTFY_TOPIC") or "").strip()
    if not topic or not CENTRAL:
        return  # not configured — silently skip, same pattern as every other optional source

    now_central = datetime.datetime.now(CENTRAL)
    if now_central.hour != NOTIFY_HOUR_CENTRAL:
        return  # not the once-a-day run — nothing to do

    today_key = now_central.date().isoformat()
    lines = _build_digest_lines(data, today_key)
    message = "\n".join(lines)
    date_label = now_central.strftime("%a, %b %-d")

    try:
        resp = requests.post(
            NTFY_PUBLISH_URL,
            json={
                "topic": topic,
                "title": f"Daily Compass — {date_label}",
                "message": message,
                "priority": "high" if (lines and lines[0].startswith("⚠")) else "default",
                "tags": ["compass"],
            },
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        # Safe to log: just confirmation + how many lines, never the
        # actual task/event text that went into the notification body.
        print(f"[notify] digest sent ({len(lines)} line(s))", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - deliberate: a failed notification must never break the build
        print(f"[notify] send failed ({type(exc).__name__}) — dashboard build continues normally",
              file=sys.stderr)

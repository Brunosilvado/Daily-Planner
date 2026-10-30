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

WHEN this sends: once a day, on the FIRST run of the day (Central time)
that happens at or after 5am AND hasn't already sent today's digest —
not "the run that happens to land at exactly 6am." That distinction
matters: GitHub's schedule trigger is explicitly best-effort and can be
delayed, especially right at the top of the hour (every one of this
project's six daily cron times used to be minute 0 — see deploy.yml's
comment on why they're now minute 17 instead). An earlier version of
this script required an EXACT hour match, and on its first real day in
production, every one of that day's six scheduled runs landed 1-5 hours
late and missed the window entirely — the digest silently never sent.

To survive that without double-sending when several of deploy.yml's
candidate runs end up firing close together, this script tracks "have I
already sent today" in a tiny marker file committed to this repo
(.github/notify-state/last-sent.txt — just a date like "2026-10-11",
nothing else) via GitHub's Contents API. Each run after 5am Central
reads that file; if today's date isn't in it yet, it CLAIMS the day
first (commits the new date) and only sends if that claim succeeds —
see "Claim-before-send" below for why that ordering matters. A run
before 5am, or a later run on a day already claimed, does nothing.

  Earlier version, and why it changed (2026-10-30): this used to store
  the date in a GitHub Actions repository VARIABLE instead of a
  committed file, using the "actions: write" permission. That silently
  never worked — GitHub's own docs/community confirm the default
  GITHUB_TOKEN is blocked from the Actions variables API entirely,
  REGARDLESS of what permissions the workflow declares. So the state
  check always failed, always returned "unknown," and EVERY eligible
  run each day sent its own notification independently — normally just
  an occasional duplicate, but on a day GitHub's scheduler fell behind
  and fired several overdue runs in a burst (confirmed: 6 runs in 31
  minutes on 2026-10-30), that meant 6 near-simultaneous notifications.
  Committing a file is something the default GITHUB_TOKEN can actually
  do (with "contents: write" — see deploy.yml), so this version uses
  that instead, with no new credential or secret needed.

  Claim-before-send: the marker gets committed BEFORE the ntfy POST
  fires, not after. If the commit fails (including losing a race to
  another near-simultaneous run — the Contents API requires the
  current file's exact sha to update it, so a stale attempt is
  rejected rather than silently overwriting), this run does NOT send,
  on the theory that another run is already handling today or just
  did. That's a deliberate change from "send first, record second":
  the old order meant a run that got cut off between those two steps
  could cause exactly the kind of duplicate this rewrite exists to
  fix. The trade-off is a slightly higher chance of a rare missed day
  if the commit step itself fails for an unrelated reason (network
  hiccup, GitHub outage) — accepted deliberately, since duplicates
  flooding a phone are the worse experience of the two.

If GITHUB_TOKEN or GITHUB_REPOSITORY aren't available (e.g. running
this script locally rather than in Actions), the state check is
skipped entirely and this falls back to the old exact-hour behavior —
degraded, but never crashes the build over something this optional.

Testing it on demand: the Actions tab's "Run workflow" button (manual
workflow_dispatch) has a "force_notify" checkbox. Ticking it sets the
FORCE_NTFY_SEND env var for that one run only, which skips BOTH the
5am-Central check and the already-sent-today check — useful for
confirming NTFY_TOPIC actually reaches your phone without waiting. A
forced send never touches the marker file, so it can't cause that day's
real digest to be skipped. A normal scheduled run never sets
FORCE_NTFY_SEND, so none of this affects the once-a-day timing.

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
  - Tap-to-open: the notification carries a "click" link straight to
    the dashboard (so tapping it opens the page instead of just
    showing the digest text). That means the dashboard's secret slug
    — the one thing standing between this public repo and a stranger
    finding the live page — ALSO now passes through ntfy.sh's servers
    on every send, not just task/event names. Same trust model as the
    topic name: ntfy.sh could see it, same as it already sees the
    digest content. If that's more exposure than the tap-to-open
    convenience is worth, the fix is to drop the "click" field below
    (or unset NTFY_TOPIC entirely) — either way nothing else here
    changes.
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
GITHUB_API_URL = "https://api.github.com"
TIMEOUT_SECONDS = 15
# Earliest Central (hour, minute) a scheduled run is allowed to send
# today's digest. Paired with deploy.yml's dense 10:07-12:47 UTC morning
# cluster, this picks out the first candidate at/after 6:07am Central
# under normal conditions (not an exact-match target — just a floor, so
# an early 5am-ish candidate doesn't send well ahead of the "6am" the
# cluster is built around). If every morning candidate gets delayed
# past this floor on a given day, the digest still goes out on whichever
# run (even the afternoon/evening ones) is the first to notice it hasn't
# sent yet — see the module docstring.
EARLIEST_SEND_TIME_CENTRAL = (5, 50)  # (hour, minute)
# Path (relative to the repo root) of the tiny marker file this uses to
# claim "today's digest is handled." Deliberately outside site/, scripts/,
# and anything else deploy.yml's `push:` trigger watches, so this script
# committing it never kicks off an extra, unwanted deploy run.
NOTIFY_STATE_PATH = ".github/notify-state/last-sent.txt"

try:
    from zoneinfo import ZoneInfo
    CENTRAL = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover - defensive only
    CENTRAL = None


def _github_api_headers():
    """Headers for GitHub's REST API, authenticated with this run's
    short-lived GITHUB_TOKEN. Returns None if that token (or the repo
    name GitHub also sets automatically) isn't available — e.g. a local
    run outside Actions — so callers can fall back gracefully."""
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if not token or not repo:
        return None, None
    return repo, {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_state_file():
    """Reads the marker file's current content + sha from this repo via
    GitHub's Contents API. Returns (date_string_or_None, sha_or_None).
    sha is None when the file doesn't exist yet (first run ever) — the
    caller needs that for a PUT's conflict check either way. Returns
    (None, None) on any failure (no token, network hiccup, etc.) —
    callers treat that "unknown" the same as "never sent," which risks
    an extra send rather than a missed one, matching this module's
    long-standing bias on lookup failures specifically (see
    "Claim-before-send" above for why the CLAIM step's own failures are
    handled the opposite way)."""
    import base64
    repo, headers = _github_api_headers()
    if not headers:
        return None, None
    try:
        resp = requests.get(
            f"{GITHUB_API_URL}/repos/{repo}/contents/{NOTIFY_STATE_PATH}",
            headers=headers,
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code == 404:
            return None, None  # never sent before — normal on first run
        resp.raise_for_status()
        body = resp.json()
        content = base64.b64decode(body.get("content", "")).decode("utf-8", "replace").strip()
        return (content or None), body.get("sha")
    except Exception:  # noqa: BLE001 - deliberate: a lookup failure must never block a real send
        return None, None


def _claim_today(date_key, sha):
    """Tries to commit `date_key` into the marker file, claiming today as
    "being handled by this run." `sha` is the file's current sha from
    _get_state_file() (None if the file doesn't exist yet). Returns True
    only if the commit actually succeeds — including GitHub rejecting it
    because another near-simultaneous run's sha is now stale, which is
    the Contents API's own built-in race protection (a PUT's `sha` must
    match the file's current sha, or it's rejected as a 409/422 conflict
    rather than silently overwriting). Any failure returns False, which
    makes the caller skip sending — see the module docstring's
    "Claim-before-send" note for why a failure here must NOT fall back
    to sending anyway."""
    repo, headers = _github_api_headers()
    if not headers:
        return False
    import base64
    payload = {
        "message": f"notify: mark {date_key} as sent [skip ci]",
        "content": base64.b64encode(date_key.encode("utf-8")).decode("ascii"),
    }
    if sha:
        payload["sha"] = sha
    try:
        resp = requests.put(
            f"{GITHUB_API_URL}/repos/{repo}/contents/{NOTIFY_STATE_PATH}",
            headers=headers,
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 - deliberate: see docstring
        print(f"[notify] couldn't claim today ({type(exc).__name__}) "
              f"— skipping send this run; another run may already have it, "
              f"or today's digest may be missed if not",
              file=sys.stderr)
        return False


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


def maybe_send_digest(data, dashboard_url=None):
    """Call this once per build, after `data` (the same dict build_site.py
    writes to data.json) is ready. Does nothing unless NTFY_TOPIC is set
    AND this happens to be the ~6am-Central run — see the module
    docstring for both of those conditions.

    dashboard_url, if given, becomes the notification's tap-to-open
    link — see the module docstring's "Tap-to-open" security note for
    what that trades off. Pass None (the default) to leave the
    notification as plain text with no click-through."""
    topic = (os.environ.get("NTFY_TOPIC") or "").strip()
    if not topic or not CENTRAL:
        return  # not configured — silently skip, same pattern as every other optional source

    now_central = datetime.datetime.now(CENTRAL)
    forced = (os.environ.get("FORCE_NTFY_SEND") or "").strip().lower() == "true"
    today_key = now_central.date().isoformat()

    if not forced:
        if (now_central.hour, now_central.minute) < EARLIEST_SEND_TIME_CENTRAL:
            return  # too early in the day — wait for a later run
        sent_date, sha = _get_state_file()
        if sent_date == today_key:
            return  # a run earlier today already claimed (and sent) it
        # Claim BEFORE sending — see the module docstring's
        # "Claim-before-send" note. If this fails (including losing a
        # race to another near-simultaneous run), skip the send rather
        # than risk a duplicate.
        if not _claim_today(today_key, sha):
            return

    lines = _build_digest_lines(data, today_key)
    message = "\n".join(lines)
    date_label = now_central.strftime("%a, %b %-d")
    if forced:
        message = "(Test send — triggered manually)\n" + message

    try:
        # ntfy's JSON publish API requires priority as an INTEGER 1-5 (1=min,
        # 3=default, 5=max) — NOT the string "high"/"default" the header-based
        # publish API accepts. Sending a string here is what caused the first
        # test send to fail with a generic "request body must be valid JSON"
        # 400 error: ntfy's JSON decoder chokes on the type mismatch and
        # reports it as a parse failure rather than a field-specific one.
        NTFY_PRIORITY_URGENT = 4  # "high" — shown with a red bar, bypasses some DND
        NTFY_PRIORITY_DEFAULT = 3  # normal priority, no special treatment
        payload = {
            "topic": topic,
            "title": f"Daily Compass — {date_label}",
            "message": message,
            "priority": NTFY_PRIORITY_URGENT if (lines and lines[0].startswith("⚠")) else NTFY_PRIORITY_DEFAULT,
            "tags": ["compass"],
        }
        # Tap-to-open — see the module docstring's "Tap-to-open" security
        # note. Only added when build_site.py could work out the dashboard's
        # URL (it always can inside GitHub Actions; omitted entirely for a
        # local test run, which just means no click-through there).
        if dashboard_url:
            payload["click"] = dashboard_url
        resp = requests.post(
            NTFY_PUBLISH_URL,
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        # Safe to log: just confirmation + how many lines, never the
        # actual task/event text that went into the notification body.
        print(f"[notify] digest sent ({len(lines)} line(s))", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - deliberate: a failed notification must never break the build
        # Safe to log: an HTTP status code and a response body's first 200
        # characters from ntfy.sh's own error message are not secrets (they
        # never echo back the topic name or digest text on an error) — this
        # extra detail is what actually lets a failure get diagnosed instead
        # of just "something went wrong."
        status = getattr(getattr(exc, "response", None), "status_code", None)
        body_snippet = ""
        if getattr(exc, "response", None) is not None:
            try:
                body_snippet = exc.response.text[:200]
            except Exception:  # pragma: no cover - defensive only
                pass
        print(
            f"[notify] send failed ({type(exc).__name__}, status={status}) "
            f"body={body_snippet!r} — dashboard build continues normally",
            file=sys.stderr,
        )

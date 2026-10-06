# Daily Planner — your Daily Compass dashboard

**Live dashboard:** ask Claude for the link (it's not written down here on
purpose — see "Why the link isn't in this file" below).

## What this actually is, in plain terms

This repo runs your "Daily Compass" dashboard — the Today / Tomorrow /
Monthly / Money page you and Claudia check on your phones. It used to live
as a Claude artifact, which only updated when you asked Claude to refresh
it and only worked while your computer was on. This version fixes both:

- **It's hosted for free** on GitHub Pages (GitHub's free website hosting).
- **It refreshes itself automatically**, six times a day, using GitHub
  Actions (GitHub's free "run this on a schedule" robot). Your computer
  can be off; nothing here depends on it.
- **The page itself never changes** — only the data behind it does. A
  robot visits your calendar/budget/to-do accounts, writes the latest
  numbers to one small file, and the page you already have bookmarked
  just shows whatever's in that file.

You will basically never need to open this GitHub repo or touch any code.
It's documented here for the rare case you want to understand what's
running, or if something ever needs fixing.

## The pieces, in plain English

| Folder / file | What it is |
|---|---|
| `site/` | The dashboard itself — the page design, layout and buttons. This almost never needs to change. |
| `scripts/` | Small programs that fetch your Calendar, YNAB and To Do data and package it into one file the dashboard reads. |
| `.github/workflows/deploy.yml` | The schedule and instructions for GitHub's free robot: "run the scripts, then publish the result." |
| **Secrets** (Settings → Secrets and variables → Actions) | Where your private keys/tokens live — never visible in this repo's files, never visible to anyone browsing GitHub, only usable by the robot while it runs. |

**Glossary**, if any of these words come up:
- **Repo** — a project folder on GitHub. This one is called `Daily-Planner`.
- **Workflow / Action** — GitHub's name for "a robot that runs a set of
  steps automatically," either on a timer or when you click a button.
- **Secret** — a password/token stored by GitHub in a locked box. Only the
  robot can use it while running; it's never shown in any file or page.
- **Pages** — GitHub's free website hosting. What turns this repo into an
  actual web page with a URL.
- **Deploy** — publishing the latest version of the page so phones see it.

## Why the link isn't in this file

This repo is public (required for the free hosting), so anything written
here can be seen by anyone on the internet. The real dashboard link
includes a long random code that works like a password — treat the full
URL the way you'd treat a password, and share it with Claudia directly
rather than through anything public. Ask Claude for it any time; it's
stored as a repo secret (`PAGES_SLUG`), not written in any file here.

## Current status (as of this setup)

- ✅ Pages hosting: on
- ✅ Scheduled refresh: on, runs 6×/day (covers both summer/winter time
  automatically, so no manual clock-change fix twice a year)
- ✅ First successful publish: confirmed working
- ✅ **All three data sources connected:** YNAB (money), Google Calendar,
  and Microsoft To Do are all live. Every section shows real data now —
  nothing here is faked or placeholder.

## If a connection ever needs refreshing

Each connection runs on a long-lived token minted once through a
one-time sign-in (never through anything typed in a chat with Claude).
If a section ever reverts to its honest "not connected yet" state after
working fine for a while, the fix is just re-running that source's local
consent script once more for a fresh token:

1. **YNAB** (money) — generate a new Personal Access Token in YNAB's own
   settings (Account Settings → Developer Settings) and update the
   `YNAB_TOKEN` secret.
2. **Google Calendar** — re-run `scripts/local_auth/google_calendar_token.py`
   on your own computer and update `GOOGLE_OAUTH_REFRESH_TOKEN`.
3. **Microsoft To Do** — re-run `scripts/local_auth/ms_todo_token.py` on
   your own computer and update `MS_GRAPH_REFRESH_TOKEN`.

Whatever a script prints, it goes straight into the matching GitHub
secret — never pasted into a chat with Claude, since that's the one
place it stops being private.

Claude can walk through any of these again whenever needed — just ask.

## Security notes

A full security review was done on this project (code, GitHub settings,
and the deploy pipeline). Here's what it found, in plain terms — what's
already fixed, what's a smaller residual risk, and one decision for you.

### The main finding: build artifacts are briefly downloadable

Every time the robot runs, it packages the finished page (including the
real secret link and the live data.json — your Calendar/YNAB/To Do
figures for that run) into something GitHub calls a "build artifact"
before publishing it. That packaged copy is listed under this repo's
**Actions** tab, and because this repo is public, **any signed-in GitHub
account** — not just someone who already has your dashboard link — could
browse to that Actions run and download it while it's still there.

This doesn't affect the real published page (`_site/<slug>/...`), which
stays exactly as protected as described above — it's specifically the
leftover packaging step that's briefly exposed.

**What's already been fixed:** the artifact is now set to delete itself
after 1 day (`retention-days: 1` in `.github/workflows/deploy.yml`) —
that's the shortest time GitHub allows. Since the robot runs 6×/day, a
fresh one replaces the old one well before that day is up anyway, so in
practice very little is ever sitting there.

**What would close this fully:** moving data.json out of the Pages build
entirely — for example, having it live in a private GitHub Gist instead,
fetched by the page at the address only you know, with nothing about the
Gist's address ever written into any file that gets built or committed.
That's a real rework of a few files and a new credential, which is a
large-enough change that it's worth you deciding on it deliberately
rather than Claude just doing it — ask Claude any time you want to take
that on, or to talk through the trade-off again.

**Until then:** the 1-day retention limit is the accepted trade-off —
small residual exposure window, no new credentials or rework needed.

### Smaller findings

- **The secret link (`PAGES_SLUG`) should be long and random.** The
  build now warns (in the Actions log only, never on the page itself) if
  it's shorter than 20 random characters — short or guessable slugs are
  easier for a stranger to stumble onto or brute-force. Ask Claude to
  generate a fresh, longer one and walk you through rotating it if
  you'd like.
- **No branch protection is set on `main`.** Right now, anyone with
  write access to the repo (just you, today) could push directly to the
  branch that gets deployed, with no review step. Low risk while it's
  only you, but a one-click setting in GitHub (Settings → Branches) if
  you ever add a collaborator.
- **No automatic dependency updates.** The Python packages this project
  uses (like `requests`) don't get security patches automatically. GitHub's
  free Dependabot feature can be turned on (Settings → Code security) to
  open a pull request automatically when one needs updating.

### What's already solid (confirmed, not just assumed)

- Every API call this project makes is read-only (GET) — Calendar, YNAB,
  and To Do credentials are all scoped so this code can't change or
  delete anything in those accounts even if a token were misused.
- No secret (token, client ID/secret, calendar ID) is ever written to
  this repository's files or git history, logged in full, or echoed back
  on the dashboard page — only short, non-secret diagnostics (lengths,
  counts, machine error codes) ever reach a log.
- Every bit of text that comes from an outside source (a calendar event
  title, a task name) is written to the page as plain text, never as
  raw HTML — so a maliciously-named event or task can't inject anything
  into the page.
- The page is kept out of search engines on two independent layers
  (`robots.txt` plus a `noindex` tag on every page), and the deployment
  status API GitHub itself exposes was checked by hand and only ever
  reveals the harmless root URL, never the secret slug.

## If something looks broken

- Check the **Actions** tab on GitHub (top of the repo page) — every run
  is listed there with a green check or red X. Click a red X to see what
  failed.
- Nothing you do here can break your Calendar, YNAB or To Do accounts —
  this only ever *reads* from them, never changes anything there.
- Worst case, nothing refreshes and the dashboard just shows slightly
  stale data — it never shows wrong or made-up data.

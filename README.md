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

## If something looks broken

- Check the **Actions** tab on GitHub (top of the repo page) — every run
  is listed there with a green check or red X. Click a red X to see what
  failed.
- Nothing you do here can break your Calendar, YNAB or To Do accounts —
  this only ever *reads* from them, never changes anything there.
- Worst case, nothing refreshes and the dashboard just shows slightly
  stale data — it never shows wrong or made-up data.

# Daily Planner

A personal Today/Tomorrow/Monthly/Money dashboard, hosted free on GitHub
Pages and kept current by a scheduled GitHub Action — no computer needs to
stay on, and nothing lives in a Claude artifact.

## How it works

- `site/` holds the generic dashboard (HTML/CSS/JS). No personal data and
  no secret URL path ever live here — this repo is public.
- `scripts/build_site.py` runs inside GitHub Actions on a schedule. It reads
  the `PAGES_SLUG` secret, assembles the real site under `_site/<slug>/`,
  and fills `data.json` with fresh data from `scripts/fetch_*.py`.
- `_site/` is never committed — `actions/upload-pages-artifact` ships it
  straight to the Pages environment, so the slug and the live data
  (calendar items, cash flow, tasks) never touch git history.
- The repo-root Pages URL (`https://brunosilvado.github.io/Daily-Planner/`)
  is a deliberate decoy with nothing on it. The real dashboard is only at
  `.../<PAGES_SLUG>/` — treat that full URL like a password.

## One-time setup still needed

1. **Enable Pages** (Settings -> Pages -> Build and deployment -> Source:
   **GitHub Actions**).
2. **Add repository secrets** (Settings -> Secrets and variables ->
   Actions):
   - `PAGES_SLUG` — the random path segment for the real URL.
   - `YNAB_TOKEN`, `YNAB_BUDGET_ID` — from YNAB's Developer Settings.
   - `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
     `GOOGLE_OAUTH_REFRESH_TOKEN` — from a Google Cloud OAuth client with
     Calendar offline access.
   - `MS_GRAPH_CLIENT_ID`, `MS_GRAPH_REFRESH_TOKEN` — from the Azure AD app
     registration (device-code flow, delegated `Tasks.Read`).
3. Until a given secret is set, that section of the dashboard just shows
   its honest "not connected yet" state — nothing fake is ever shown.

## Running it manually

Actions tab -> "Build and deploy dashboard" -> **Run workflow**, any time
you don't want to wait for the next scheduled refresh.

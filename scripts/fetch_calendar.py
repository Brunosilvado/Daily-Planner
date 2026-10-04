"""
Google Calendar fetcher — Phase 2.

Will use a refresh token minted once via Google's OAuth consent screen
("offline access") and stored as the GitHub Secrets below. None of these
are read from any file in this repo; they only exist as encrypted
repository secrets, injected as environment variables at job run time.

Required secrets (not yet configured):
  GOOGLE_OAUTH_CLIENT_ID
  GOOGLE_OAUTH_CLIENT_SECRET
  GOOGLE_OAUTH_REFRESH_TOKEN

Until those are set, this returns None and the dashboard shows its honest
"Calendar isn't connected yet" state.
"""
import os


def get_calendar_data():
    if not os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN"):
        return None

    # TODO (Phase 2): exchange the refresh token for an access token,
    # call the Calendar API for each calendar ID, and build:
    #   {"calendarConnected": True, "todoConnected": False,
    #    "asOf": "<human readable Central time>",
    #    "items": {"YYYY-MM-DD": [{"time": "...", "text": "..."}]}}
    return None

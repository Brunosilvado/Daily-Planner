"""
Microsoft To Do fetcher — Phase 2.

Uses Microsoft Graph via the Azure AD app registration already created
(client ID 807fbd85-9d78-43c0-b250-08a46a09259c, public client, device-code
flow, delegated Tasks.Read). A one-time device-code consent run mints a
refresh token, which then gets stored as a GitHub Secret and silently
renewed on each job run (Graph refresh tokens are long-lived and rotate).

Required secrets (not yet configured):
  MS_GRAPH_CLIENT_ID
  MS_GRAPH_REFRESH_TOKEN

Until those are set, this returns None and the dashboard shows its honest
"To Do isn't connected yet" state.
"""
import os


def get_tasks_data():
    if not os.environ.get("MS_GRAPH_REFRESH_TOKEN"):
        return None

    # TODO (Phase 2): exchange the refresh token for an access token against
    # https://login.microsoftonline.com/common/oauth2/v2.0/token, call
    # https://graph.microsoft.com/v1.0/me/todo/lists and each list's /tasks
    # (filter status ne 'completed'), and build:
    #   {"asOf": "<human readable Central time>",
    #    "groups": [{"list": "...", "items": [{"text": "...", "overdue": bool, "due": "..."}]}]}
    return None

"""
Run this on YOUR OWN computer, once. It never runs in GitHub Actions and
nothing it does is sent anywhere except directly to Google.

What it does:
  1. Asks for your OAuth Client ID and Client Secret (from Google Cloud
     Console) — typed here, in your own terminal, never shared with
     Claude or anyone else.
  2. Opens your browser to Google's consent screen, asking for read-only
     Calendar access.
  3. After you approve, Google redirects back to a tiny local web server
     this script starts on your own machine (127.0.0.1) to catch the
     result — nothing leaves your computer except the direct call to
     Google in step 4.
  4. Exchanges that for a refresh token and prints it to YOUR terminal.

What you do next: copy that refresh token straight into the GitHub secret
GOOGLE_OAUTH_REFRESH_TOKEN (Settings -> Secrets and variables -> Actions)
on https://github.com/Brunosilvado/Daily-Planner — not into any chat.

Requires only Python's standard library — nothing to pip install.
"""
import http.server
import json
import urllib.parse
import urllib.request
import webbrowser

SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class _CodeCatcher(http.server.BaseHTTPRequestHandler):
    code = None

    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CodeCatcher.code = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body>Done &mdash; you can close this tab and "
                          b"go back to your terminal.</body></html>")

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet


def main():
    client_id = input("Paste your OAuth Client ID: ").strip()
    client_secret = input("Paste your OAuth Client Secret: ").strip()

    server = http.server.HTTPServer(("127.0.0.1", 0), _CodeCatcher)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}/"

    auth_url = AUTH_BASE + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",  # forces a refresh token even on a repeat run
    })

    print("\nOpening your browser to sign in and approve read-only Calendar access...")
    print("If it doesn't open automatically, paste this URL into a browser:\n")
    print(auth_url, "\n")
    webbrowser.open(auth_url)

    server.handle_request()  # blocks until the one redirect comes in
    code = _CodeCatcher.code
    if not code:
        print("No authorization code received — did you approve the consent screen?")
        return

    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())

    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        print("No refresh_token in the response — this can happen if you've already")
        print("granted this app access before. In Google's consent screen this script")
        print("just opened, check if there's an option to remove prior access, or")
        print("remove this app's access at https://myaccount.google.com/permissions")
        print("and run this script again.")
        return

    print("\nSuccess. Your refresh token is below.")
    print("Copy it directly into the GitHub secret GOOGLE_OAUTH_REFRESH_TOKEN")
    print("(Settings -> Secrets and variables -> Actions) — not into any chat:\n")
    print(refresh_token)


if __name__ == "__main__":
    try:
        main()
    finally:
        # If this was double-clicked instead of run from an already-open
        # terminal, Windows closes the window the instant the script ends
        # — which would wipe the refresh token off the screen before it
        # could be copied. This keeps the window open until a key is
        # pressed, regardless of how the script was started.
        input("\nPress Enter to close this window...")

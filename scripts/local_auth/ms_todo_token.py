"""
Run this on YOUR OWN computer, once. It never runs in GitHub Actions and
nothing it does is sent anywhere except directly to Microsoft.

What it does:
  1. Asks Microsoft for a short "device code" tied to the Azure app
     already registered for this project (public client, no secret
     needed — that's what "public client" means).
  2. Shows you a short code and a web address
     (https://microsoft.com/devicelogin). You open that address on any
     device, sign in with your Microsoft account, type the code, and
     approve read-only access to your To Do tasks.
  3. The moment you approve, this script (which has been quietly asking
     Microsoft "are they done yet?" every few seconds) gets back a
     refresh token and prints it to YOUR terminal.

What you do next: copy that refresh token straight into the GitHub secret
MS_GRAPH_REFRESH_TOKEN (Settings -> Secrets and variables -> Actions) on
https://github.com/Brunosilvado/Daily-Planner — not into any chat.

Requires only Python's standard library — nothing to pip install.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_CLIENT_ID = "807fbd85-9d78-43c0-b250-08a46a09259c"
SCOPE = "https://graph.microsoft.com/Tasks.Read offline_access"
DEVICE_CODE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


def _post(url, data):
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode(data).encode(), method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main():
    client_id = input(
        f"Paste the app's Client ID, or press Enter to use the one already "
        f"set up for this project ({DEFAULT_CLIENT_ID}): "
    ).strip() or DEFAULT_CLIENT_ID

    device = _post(DEVICE_CODE_URL, {
        "client_id": client_id,
        "scope": SCOPE,
    })

    print("\n" + device["message"] + "\n")
    print(f"(That's: go to {device['verification_uri']} and enter code "
          f"{device['user_code']})\n")
    print("Waiting for you to approve in the browser...")

    interval = device.get("interval", 5)
    expires_at = time.time() + device.get("expires_in", 900)

    while time.time() < expires_at:
        time.sleep(interval)
        try:
            token = _post(TOKEN_URL, {
                "client_id": client_id,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device["device_code"],
            })
        except urllib.error.HTTPError as e:
            body = json.loads(e.read())
            error = body.get("error")
            if error == "authorization_pending":
                continue  # not yet approved — keep waiting
            if error == "slow_down":
                interval += 5
                continue
            print(f"\nSign-in failed: {body.get('error_description', error)}")
            return
        else:
            refresh_token = token.get("refresh_token")
            if not refresh_token:
                print("\nNo refresh_token in the response — unexpected. Full response:")
                print(json.dumps(token, indent=2))
                return
            print("\nSuccess. Your refresh token is below.")
            print("Copy it directly into the GitHub secret MS_GRAPH_REFRESH_TOKEN")
            print("(Settings -> Secrets and variables -> Actions) — not into any chat:\n")
            print(refresh_token)
            print("\nAlso make sure the GitHub secret MS_GRAPH_CLIENT_ID is set to:")
            print(client_id)
            return

    print("\nTimed out waiting for approval — run this again when you're ready.")


if __name__ == "__main__":
    try:
        main()
    finally:
        # Keeps the window open if this was double-clicked rather than run
        # from an already-open terminal (see the same fix in the Google
        # script for why this matters on Windows).
        input("\nPress Enter to close this window...")

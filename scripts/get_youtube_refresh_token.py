"""One-time, LOCAL-ONLY helper: run this yourself once to mint a YouTube OAuth refresh token.

This opens a browser for you to log into the Google account that owns the target YouTube
channel and grant upload access. Never run this in CI -- it needs an interactive browser.
After it prints a refresh token, paste that value into the YT_REFRESH_TOKEN GitHub secret.

Usage:
    set YT_CLIENT_ID=...          (or export on macOS/Linux)
    set YT_CLIENT_SECRET=...
    python scripts/get_youtube_refresh_token.py
"""

import os

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    client_config = {
        "installed": {
            "client_id": os.environ["YT_CLIENT_ID"],
            "client_secret": os.environ["YT_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\nSave this as the YT_REFRESH_TOKEN GitHub secret:\n")
    print(creds.refresh_token)


if __name__ == "__main__":
    main()

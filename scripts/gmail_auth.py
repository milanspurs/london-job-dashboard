"""One-off helper: get a Gmail refresh token for the GitHub Actions secrets.

Run on YOUR computer (not in GitHub):

    pip install google-auth-oauthlib
    python scripts/gmail_auth.py path/to/client_secret.json

A browser window opens; sign in and allow "Manage drafts and send emails"
(gmail.compose — Google has no narrower drafts-only scope; this project's code
only ever calls the drafts.create endpoint). The script prints the three values
to paste into GitHub secrets. Nothing is written to disk.
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    with open(sys.argv[1]) as f:
        cfg = json.load(f)
    flow = InstalledAppFlow.from_client_config(cfg, SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    info = cfg.get("installed") or cfg.get("web")
    print("\nAdd these as GitHub repository secrets (Settings > Secrets and variables > Actions):\n")
    print(f"GMAIL_CLIENT_ID      = {info['client_id']}")
    print(f"GMAIL_CLIENT_SECRET  = {info['client_secret']}")
    print(f"GMAIL_REFRESH_TOKEN  = {creds.refresh_token}")
    print("\nOptional: GMAIL_TO = the address to pre-fill in each draft's To field.")


if __name__ == "__main__":
    main()

import os
import sys
import subprocess
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    print("=" * 60)
    print("YOUTUBE OAUTH REFRESH TOKEN GENERATOR & SECRET UPDATER")
    print("=" * 60)
    
    client_id = "751457863885-pehk2927qh7t49akhi552q4vjddm4nlt.apps.googleusercontent.com"
    client_secret = "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"
    
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080/"]
        }
    }
    
    print("\nOpening browser for YouTube channel authorization...")
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=8080, open_browser=True, prompt="consent", access_type="offline")
    
    refresh_token = creds.refresh_token
    if not refresh_token:
        print("Error: No refresh token returned. Ensure prompt='consent' and access_type='offline'.")
        sys.exit(1)
        
    print("\n✅ New Refresh Token successfully generated!")
    print(f"Token: {refresh_token[:15]}...")
    
    repos = [
        "arunachalamvenkatachalapathy-dev/market-debunk-autonomous",
        "arunachalamvenkatachalapathy-dev/market-debunk-tamil"
    ]
    
    for repo in repos:
        print(f"\nUpdating GitHub Secret 'YT_REFRESH_TOKEN' in {repo}...")
        cmd = ["gh", "secret", "set", "YT_REFRESH_TOKEN", "-R", repo, "--body", refresh_token]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"  ✅ Successfully updated secret in {repo}")
        else:
            print(f"  ❌ Error updating secret in {repo}: {res.stderr}")

        # Update YT_CLIENT_ID and YT_CLIENT_SECRET as well to ensure full alignment
        subprocess.run(["gh", "secret", "set", "YT_CLIENT_ID", "-R", repo, "--body", client_id], capture_output=True)
        subprocess.run(["gh", "secret", "set", "YT_CLIENT_SECRET", "-R", repo, "--body", client_secret], capture_output=True)

    print("\n🚀 Re-triggering GitHub Action workflows with fresh token...")
    for repo in repos:
        cmd_run = ["gh", "api", f"repos/{repo}/actions/workflows/daily_video.yml/dispatches", "-f", "ref=master"]
        res = subprocess.run(cmd_run, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"  🚀 Workflow successfully triggered in {repo}")
        else:
            print(f"  ⚠️ Error triggering workflow in {repo}: {res.stderr}")

if __name__ == "__main__":
    main()

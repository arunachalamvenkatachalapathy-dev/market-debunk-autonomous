import os
import sys
import subprocess
import json
from google_auth_oauthlib.flow import InstalledAppFlow

# YouTube Data API v3 Upload Scope
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    print("=" * 60)
    print("YOUTUBE OAUTH REFRESH TOKEN AUTO-UPDATER")
    print("=" * 60)
    
    # Check if client_secrets.json exists locally
    client_secrets_path = "client_secrets.json"
    if not os.path.exists(client_secrets_path):
        # Allow pasting client_id and client_secret if file isn't present
        client_id = input("Enter your YT_CLIENT_ID: ").strip()
        client_secret = input("Enter your YT_CLIENT_SECRET: ").strip()
        
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:8080/"]
            }
        }
        with open(client_secrets_path, "w") as f:
            json.dump(client_config, f)
            
    # Launch OAuth flow
    print("\nOpening browser for YouTube authorization...")
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
    creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")
    
    refresh_token = creds.refresh_token
    if not refresh_token:
        print("Error: No refresh token returned. Ensure prompt='consent' and access_type='offline'.")
        sys.exit(1)
        
    print("\n✅ New Refresh Token successfully generated!")
    
    # Update GitHub Secrets automatically using gh CLI
    repos = [
        "arunachalamvenkatachalapathy-dev/market-debunk-autonomous",
        "arunachalamvenkatachalapathy-dev/market-debunk-tamil"
    ]
    
    for repo in repos:
        print(f"Updating GitHub Secret 'YT_REFRESH_TOKEN' in {repo}...")
        cmd = ["gh", "secret", "set", "YT_REFRESH_TOKEN", "-R", repo, "--body", refresh_token]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"  ✅ Successfully updated secret in {repo}")
        else:
            print(f"  ❌ Error updating secret in {repo}: {res.stderr}")

    print("\n🚀 Re-triggering GitHub Action workflows with fresh token...")
    for repo in repos:
        subprocess.run(["gh", "workflow", "run", "daily_video.yml", "-R", repo])
        print(f"  ✅ Triggered daily_video.yml in {repo}")

if __name__ == "__main__":
    main()

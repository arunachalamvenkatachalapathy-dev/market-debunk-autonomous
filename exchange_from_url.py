import sys
import subprocess
import requests
from urllib.parse import urlparse, parse_qs

CLIENT_ID = "751457863885-pehk2927qh7t49akhi552q4vjddm4nlt.apps.googleusercontent.com"
CLIENT_SECRET = "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"
REDIRECT_URI = "http://localhost:8080/"

def exchange_raw_code(code_str, redirect_uri=REDIRECT_URI):
    # Clean code
    code = code_str.strip()
    if "code=" in code:
        parsed = parse_qs(urlparse(code).query)
        if "code" in parsed:
            code = parsed["code"][0]
            
    print(f"Exchanging code: {code[:15]}...")
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri
    }
    res = requests.post(token_url, data=data)
    print("Response status:", res.status_code)
    res_data = res.json()
    print("Response:", res_data)
    
    refresh_token = res_data.get("refresh_token")
    if refresh_token:
        print("\n✅ SUCCESS! Refresh Token generated:", refresh_token[:15])
        repos = [
            "arunachalamvenkatachalapathy-dev/market-debunk-autonomous",
            "arunachalamvenkatachalapathy-dev/market-debunk-tamil"
        ]
        for repo in repos:
            print(f"Updating secret in {repo}...")
            subprocess.run(["gh", "secret", "set", "YT_REFRESH_TOKEN", "-R", repo, "--body", refresh_token], capture_output=True)
            subprocess.run(["gh", "secret", "set", "YT_CLIENT_ID", "-R", repo, "--body", CLIENT_ID], capture_output=True)
            subprocess.run(["gh", "secret", "set", "YT_CLIENT_SECRET", "-R", repo, "--body", CLIENT_SECRET], capture_output=True)
            
            # Trigger workflow
            subprocess.run(["gh", "api", f"repos/{repo}/actions/workflows/daily_video.yml/dispatches", "-f", "ref=master"], capture_output=True)
            print(f"🚀 Triggered workflow in {repo}")
        return True
    return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        exchange_raw_code(sys.argv[1])

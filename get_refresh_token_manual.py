import sys
import subprocess
import requests

CLIENT_ID = "751457863885-pehk2927qh7t49akhi552q4vjddm4nlt.apps.googleusercontent.com"
CLIENT_SECRET = "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"
REDIRECT_URI = "http://localhost:8080/"

def exchange_code(code, code_verifier):
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI
    }
    res = requests.post(token_url, data=data)
    print("Token exchange response:", res.status_code)
    print(res.json())
    return res.json().get("refresh_token")

if __name__ == "__main__":
    print("Script helper ready.")

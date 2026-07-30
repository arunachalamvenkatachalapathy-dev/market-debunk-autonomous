import requests

client_id = "751457863885-pehk2927qh7t49akhi552q4vjddm4nlt.apps.googleusercontent.com"
client_secret = "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"
refresh_token = "4/0AXEQxIAKYvfiV15Sy4WwoFbD2JMlByxLf0Mi4wNpv5nJRvJad1dAta1tNlvTPuM0heG7dg"

print("Exchanging refresh token for access token...")
data = {
    "client_id": client_id,
    "client_secret": client_secret,
    "refresh_token": refresh_token,
    "grant_type": "refresh_token"
}

res = requests.post("https://oauth2.googleapis.com/token", data=data)
print("Status Code:", res.status_code)
print("Response Body:", res.text)

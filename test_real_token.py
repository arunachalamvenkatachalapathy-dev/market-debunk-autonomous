import requests

client_id = "751457863885-pehk2927qh7t49akhi552q4vjddm4nlt.apps.googleusercontent.com"
client_secret = "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"
refresh_token = "1//04nl-FY5Z9SCRCgYIARAAGAQSNwF-L9IrcaXU9Igpf1s0gGilMhpf2Ewu_OmMSlEcNhMSc73qXBxfUwvIJhYZl_SwMxetuXFgaww"

print("Exchanging real permanent refresh token...")
data = {
    "client_id": client_id,
    "client_secret": client_secret,
    "refresh_token": refresh_token,
    "grant_type": "refresh_token"
}

res = requests.post("https://oauth2.googleapis.com/token", data=data)
print("STATUS CODE:", res.status_code)
print("RESPONSE:", res.text)

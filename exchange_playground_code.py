import requests

client_id = "751457863885-pehk2927qh7t49akhi552q4vjddm4nlt.apps.googleusercontent.com"
client_secret = "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"
auth_code = "4/0AXEQxlBvDm2m5FistNdBmmc6UcoJn9V-GJKvwYn1Ham40LUeKefKdCVCmXU4BwHQE0yMfw"
redirect_uri = "https://developers.google.com/oauthplayground"

data = {
    "code": auth_code,
    "client_id": client_id,
    "client_secret": client_secret,
    "redirect_uri": redirect_uri,
    "grant_type": "authorization_code"
}

res = requests.post("https://oauth2.googleapis.com/token", data=data)
print("STATUS CODE:", res.status_code)
print("RESPONSE:", res.text)

import requests

client_id = "751457863885-pehk2927qh7t49akhi552q4vjddm4nlt.apps.googleusercontent.com"
client_secret = "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"
refresh_token = "1//04YaK9ELubJLzCgYIARAAGAQSNwF-L9IrAaXTAQhjP1n_5iqsB2KJQmhZNJPqnjdAYkAtUu4RAImKp8Sb9HRNC8JXlktyO8nvGz0"

print("Exchanging permanent refresh token for fresh access token...")
data = {
    "client_id": client_id,
    "client_secret": client_secret,
    "refresh_token": refresh_token,
    "grant_type": "refresh_token"
}

res = requests.post("https://oauth2.googleapis.com/token", data=data)
print("STATUS CODE:", res.status_code)
print("RESPONSE:", res.text)

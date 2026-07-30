import requests

client_id = "407408718192.apps.googleusercontent.com"
refresh_token = "1//04YaK9ELubJLzCgYIARAAGAQSNwF-L9IrAaXTAQhjP1n_5iqsB2KJQmhZNJPqnjdAYkAtUu4RAImKp8Sb9HRNC8JXlktyO8nvGz0"

print("Testing Playground Client ID...")
data = {
    "client_id": client_id,
    "refresh_token": refresh_token,
    "grant_type": "refresh_token"
}

res = requests.post("https://oauth2.googleapis.com/token", data=data)
print("STATUS CODE:", res.status_code)
print("RESPONSE:", res.text)

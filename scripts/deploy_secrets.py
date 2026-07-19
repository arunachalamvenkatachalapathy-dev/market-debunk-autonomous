import os
import subprocess
from dotenv import dotenv_values

def deploy_secrets():
    print("Deploying secrets to GitHub repository...")
    secrets = dotenv_values(".env")
    
    # We only want to push the specific secrets required for the pipeline
    required_secrets = [
        "LLM_API_KEYS",
        "YOUTUBE_CLIENT_SECRET",
        "YOUTUBE_OAUTH_JSON",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID"
    ]
    
    for key in required_secrets:
        val = secrets.get(key)
        if not val:
            print(f"Warning: {key} not found in .env, skipping.")
            continue
            
        print(f"Pushing secret: {key}...")
        
        # Use subprocess to securely pipe the secret to gh
        process = subprocess.Popen(
            ["gh", "secret", "set", key],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate(input=val)
        
        if process.returncode == 0:
            print(f"SUCCESS: Successfully set {key}")
        else:
            print(f"FAILED: Failed to set {key}: {stderr}")

if __name__ == "__main__":
    deploy_secrets()

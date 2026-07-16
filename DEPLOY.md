# GCP Serverless Video Pipeline Deployment Guide

Follow these steps to deploy and automate your zero-maintenance short-form video generation channel.

---

## Step 1: Enable Google Cloud APIs
Open your Google Cloud Console terminal or install Google Cloud CLI locally, and run the following command to enable all necessary serverless, AI, and storage modules in your project:

```bash
gcloud services enable \
    run.googleapis.com \
    secretmanager.googleapis.com \
    firestore.googleapis.com \
    texttospeech.googleapis.com \
    aiplatform.googleapis.com \
    cloudscheduler.googleapis.com
```

---

## Step 2: Initialize Firestore Database
Firestore acts as our deduplication ledger.
1. Open the **Firestore** dashboard in the GCP Console.
2. Click **Create Database**.
3. Select **Native Mode** (Important: Do not select Datastore mode).
4. Set your database location (choose a region close to your primary location, e.g., `us-central1`).
5. Click **Create Database** and wait for it to complete.

---

## Step 3: Run the YouTube OAuth Helper
To upload videos to your YouTube channel, you need access credentials.
1. Open the [Google Cloud Console Credentials Screen](https://console.cloud.google.com/apis/credentials).
2. Click **Create Credentials** -> **OAuth Client ID**.
3. If prompted to configure the OAuth consent screen:
   - Select **External**.
   - Input your app name (e.g., "Shorts Media Factory") and email.
   - Under **Scopes**, search and add `https://www.googleapis.com/auth/youtube.upload`.
   - Under **Test Users**, add your YouTube channel's Google email address.
4. Back in the Credentials screen, select Application Type: **Web Application**.
5. Add Authorized Redirect URI: `http://localhost:8080/`.
6. Click **Create** and copy your **Client ID** and **Client Secret**.
7. In your local terminal, run the helper script:
   ```bash
   pip install google-auth-oauthlib
   python scripts/youtube_auth.py
   ```
8. Follow the prompts to log in and authorize the app. Copy the output **Refresh Token**, **Client ID**, and **Client Secret**.

## Step 4: Configure Secrets File in Secret Manager
Instead of creating many separate secrets, store all your variables in a single secret file. This is highly secure and prevents variable leakage.

1. Open the [GCP Secret Manager Dashboard](https://console.cloud.google.com/security/secret-manager).
2. Click **Create Secret**.
3. Name: `video_factory_secrets`
4. Under **Secret Value**, paste the entire text content of your `.env` file containing all API keys:
   ```ini
   LLM_API_KEY=your_gemini_api_studio_key
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_channel_username_or_id
   YT_CLIENT_ID=your_youtube_oauth_client_id
   YT_CLIENT_SECRET=your_youtube_oauth_client_secret
   YT_REFRESH_TOKEN=your_generated_youtube_refresh_token
   ```
5. Click **Create Secret**.

---

## Step 5: Deploy the Container to Google Cloud Run
Deploying the custom `Dockerfile` with Gunicorn and FFmpeg takes one simple command. Run this command inside the project directory. It mounts your secret file directly to `/secrets/secrets.env` inside the container:

> **SECURITY**: The `--no-allow-unauthenticated` flag ensures only authorized service accounts (like Cloud Scheduler) can invoke the pipeline. This prevents unauthorized access and API quota abuse.

```bash
gcloud run deploy video-factory \
    --source . \
    --platform managed \
    --region us-central1 \
    --no-allow-unauthenticated \
    --update-secrets=/secrets/secrets.env=video_factory_secrets:latest \
    --timeout 600 \
    --cpu 2 \
    --memory 2Gi \
    --execution-environment gen2
```

*Note: We grant 2 CPUs and 2GiB of memory, and set a timeout of 10 minutes (600 seconds) since generating and compiling video clips takes a few minutes. The `gen2` execution environment provides a larger writable `/tmp` filesystem.*

Once the deployment completes, the terminal will print a **Service URL** (e.g., `https://video-factory-xxxxxx.a.run.app`). Keep this URL for Step 6.

### Grant Cloud Scheduler Permission to Invoke

After deployment, grant the Cloud Scheduler service account permission to invoke this Cloud Run service:

```bash
# Get your project number
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')

# Grant the invoker role to the default Compute Engine service account
gcloud run services add-iam-policy-binding video-factory \
    --region us-central1 \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/run.invoker"
```

---

## Step 6: Automate Execution with Cloud Scheduler (Cron Trigger)
Configure a serverless scheduler to run the pipeline automatically twice a day (e.g., at 9 AM and 6 PM) at zero operational cost:

1. Open the **Cloud Scheduler** dashboard in the GCP Console.
2. Click **Create Job**.
3. Name: `trigger-video-shorts`
4. Region: `us-central1`
5. Schedule (Cron format): `0 9,18 * * *` (Runs daily at 9:00 AM and 6:00 PM).
6. Timezone: Choose your local timezone.
7. Target Type: **HTTP**
8. URL: Paste your Service URL from Step 5, appending `/run` at the end (e.g., `https://video-factory-xxxxxx.a.run.app/run`).
9. HTTP Method: **POST**
10. HTTP Headers: Add `Content-Type` with value `application/json`.
11. Auth Header: **Add OIDC token**
    - Service Account: Use the default Compute Engine service account (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`)
    - Audience: Your Cloud Run service URL (same URL as step 8, without the `/run` path)
12. Body (Optional JSON payload):
    ```json
    {
      "topic_title": "Daily Crypto breakout alert",
      "topic_hash": "crypto_breakout_daily"
    }
    ```
13. Click **Create**.

Your video pipeline is now fully automated and running natively on Google Cloud Platform!

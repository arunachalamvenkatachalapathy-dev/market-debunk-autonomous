#!/usr/bin/env python3
"""
scripts/setup_instagram.py

Interactive helper to exchange a short-lived Meta Graph token for a
60-day Long-Lived Access Token, find your Instagram Business Account ID,
and display the exact GitHub Secrets to configure.
"""
import requests

GRAPH_VERSION = "v23.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


def main():
    print("=" * 60)
    print("Instagram Reels Publishing Setup & Verification Tool")
    print("=" * 60)
    print("--- Prerequisites ---")
    print("1. Instagram Creator or Business Account (Free to switch in app).")
    print("2. Connected to a Facebook Page.")
    print("3. Meta App at developers.facebook.com with Instagram Graph API.")
    print("4. User Token from developers.facebook.com/tools/explorer")
    print("   with permissions: instagram_content_publish, instagram_basic, pages_show_list")
    print("=" * 60)

    token = input("\nEnter your Meta Access Token: ").strip()
    if not token:
        print("[X] Token cannot be empty.")
        return

    do_exchange = input("\nDo you want to exchange a short-lived token for a 60-day Long-Lived Token? (y/N): ").strip().lower()
    if do_exchange == "y":
        app_id = input("Enter your Meta App ID: ").strip()
        app_secret = input("Enter your Meta App Secret: ").strip()
        if not app_id or not app_secret:
            print("[X] Exchange requires both App ID and App Secret.")
            return

        res = requests.get(
            f"{BASE_URL}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": token,
            },
            timeout=15,
        )
        data = res.json()
        if "access_token" in data:
            token = data["access_token"]
            days = data.get("expires_in", 5184000) // 86400
            print(f"[v] Successfully exchanged for Long-Lived Token (valid ~{days} days).")
        else:
            print(f"[X] Exchange failed: {data}")
            return

    print("\nSearching for connected Instagram Business accounts...")
    pages_res = requests.get(
        f"{BASE_URL}/me/accounts",
        params={"access_token": token},
        timeout=15,
    )
    pages_data = pages_res.json()
    pages = pages_data.get("data", [])

    if not pages:
        print("[!] No Facebook Pages found for this user token.")
        print("Please link your Instagram account to a Facebook Page in Instagram Settings.")
        return

    ig_accounts = []
    for page in pages:
        page_id = page["id"]
        page_name = page.get("name", "Unknown")
        ig_res = requests.get(
            f"{BASE_URL}/{page_id}",
            params={"fields": "instagram_business_account{id,username,name}", "access_token": token},
            timeout=15,
        )
        ig_data = ig_res.json()
        ig_biz = ig_data.get("instagram_business_account")
        if ig_biz:
            ig_accounts.append({
                "page_name": page_name,
                "ig_user_id": ig_biz.get("id"),
                "ig_username": ig_biz.get("username", "N/A"),
                "ig_name": ig_biz.get("name", "N/A"),
            })

    if not ig_accounts:
        print("[X] No Instagram Creator/Business account linked to your Facebook Pages.")
        print("Action: Instagram -> Settings -> Account -> Switch to Professional -> Connect Facebook Page.")
        return

    print(f"\n[v] Found {len(ig_accounts)} connected Instagram account(s):")
    for i, acc in enumerate(ig_accounts, 1):
        print(f"  [{i}] @{acc['ig_username']} ({acc['ig_name']}) | Page: {acc['page_name']}")
        print(f"      INSTAGRAM_USER_ID: {acc['ig_user_id']}")

    sel = ig_accounts[0]
    if len(ig_accounts) > 1:
        choice = input(f"\nChoose account [1-{len(ig_accounts)}] (default 1): ").strip() or "1"
        sel = ig_accounts[int(choice) - 1]

    print("\n" + "=" * 60)
    print("Turnkey GitHub Secrets to add (Repo -> Settings -> Secrets -> Actions):")
    print("=" * 60)
    print("ENABLE_INSTAGRAM = true")
    print(f"INSTAGRAM_ACCESS_TOKEN = {token}")
    print(f"INSTAGRAM_USER_ID = {sel['ig_user_id']}")
    print("=" * 60)


if __name__ == "__main__":
    main()

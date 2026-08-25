"""
HeliYatra Post-Monsoon Watcher (Scrape.do + WhatsApp Template + ntfy.sh)
- Uses WhatsApp 'template' payload (bypasses 24-hour window error 131047)
- Instant URGENT alert when the portal baseline updates
"""

import os
import sys
import json
import urllib.parse
import requests
from bs4 import BeautifulSoup

TARGET_URL = "https://heliyatra.irctc.co.in"
SCRAPEDO_TOKEN = os.getenv("SCRAPEDO_TOKEN", "").strip()

# Meta WhatsApp Cloud API Credentials
WA_TOKEN = os.getenv("WA_TOKEN", "").strip()
WA_PHONE_ID = os.getenv("WA_PHONE_ID", "").strip()
WA_RECIPIENT = os.getenv("WA_RECIPIENT", "").strip()

# ntfy topic
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "heliyatra_postmonsoon_alert_2026").strip()

# Baseline snippet for diff
KNOWN_BASELINE_SNIPPET = "Shri Hemkund Sahib Helicopter ticket bookings are temporarily on hold till further instructions"


def send_meta_whatsapp_template():
    """
    Sends WhatsApp message using Meta's pre-approved 'hello_world' template.
    Bypasses the 24-hour customer window constraint (Error 131047).
    """
    if not (WA_TOKEN and WA_PHONE_ID and WA_RECIPIENT):
        print("[WHATSAPP] Skipping: Missing WA_TOKEN, WA_PHONE_ID, or WA_RECIPIENT.")
        return False

    clean_recipient = WA_RECIPIENT.replace("+", "").replace(" ", "").replace("-", "").strip()
    url = f"https://graph.facebook.com/v20.0/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json"
    }

    # Meta pre-approved template payload (delivers 24/7 anytime)
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_recipient,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {
                "code": "en_US"
            }
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        res_json = resp.json()
        print(f"[WHATSAPP TEMPLATE HTTP {resp.status_code}] Response: {json.dumps(res_json)}")

        if resp.status_code in [200, 201]:
            print(f"[WHATSAPP SUCCESS] Template message successfully delivered to {clean_recipient}!")
            return True
        else:
            print(f"[WHATSAPP FAILED] Error: {res_json.get('error', {}).get('message')}")
            return False
    except Exception as e:
        print(f"[WHATSAPP EXCEPTION] {e}")
        return False


def send_ntfy_alert(title: str, message: str, priority: str = "low"):
    """Sends push alert to ntfy.sh."""
    if not NTFY_TOPIC:
        return
    try:
        clean_title = title.encode("ascii", "ignore").decode("ascii").strip() or "HeliYatra Alert"
        url = f"https://ntfy.sh/{NTFY_TOPIC}"
        headers = {
            "Title": clean_title,
            "Priority": priority,
            "Click": TARGET_URL,
        }
        resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=15)
        print(f"[NTFY] Push status ({priority.upper()}): {resp.status_code}")
    except Exception as e:
        print(f"[NTFY ERROR] {e}")


def fetch_via_scrapedo(token: str):
    """Fetches portal HTML via Scrape.do with Indian IP proxy routing."""
    if not token:
        print("[ERROR] SCRAPEDO_TOKEN is missing in environment variables!")
        return None, 401

    encoded_url = urllib.parse.quote(TARGET_URL, safe="")
    endpoint = f"https://api.scrape.do?token={token}&url={encoded_url}&geoCode=in"

    try:
        resp = requests.get(endpoint, timeout=60)
        print(f"[SCRAPE.DO] HTTP Status: {resp.status_code}")
        return resp.text, resp.status_code
    except Exception as e:
        print(f"[SCRAPE.DO ERROR] {e}")
        return None, 500


def main():
    print("=" * 60)
    print("STARTING HELIYATRA MONITOR RUN")
    print("=" * 60)

    html_content, status_code = fetch_via_scrapedo(SCRAPEDO_TOKEN)

    if not html_content or status_code != 200:
        print(f"[CRITICAL] Portal fetch failed with HTTP {status_code}.")
        send_ntfy_alert(
            "HeliYatra Check Notice",
            f"Portal check returned HTTP {status_code}. Retrying next hour.\n{TARGET_URL}",
            priority="low"
        )
        return

    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    page_text = soup.get_text(separator=" ", strip=True)

    # Check baseline presence
    baseline_is_present = KNOWN_BASELINE_SNIPPET.lower() in page_text.lower()
    print(f"[DIFF CHECK] Baseline message found on site: {baseline_is_present}")

    if not baseline_is_present:
        # =========================================================================
        # 🚨 TRIGGER: BASELINE CHANGED / BOOKING MIGHT BE OPEN!
        # =========================================================================
        print("🚨 TRIGGER: Hold notice changed! Dispatching URGENT alerts.")

        urgent_title = "🚨 URGENT: Kedarnath Heli Booking Status Changed!"
        urgent_body = (
            "The hold notice is no longer present on the website!\n"
            "Kedarnath post-monsoon booking may be OPEN or updated.\n\n"
            f"Tap to open & book now: {TARGET_URL}"
        )
        send_ntfy_alert(urgent_title, urgent_body, priority="urgent")

        # Sends template ping on WhatsApp
        send_meta_whatsapp_template()

    else:
        # =========================================================================
        # ℹ️ HOURLY DIGEST: BOOKING NOT OPEN YET
        # =========================================================================
        print("[DIGEST] Booking not opened yet. Sending concise status digest.")

        digest_title = "HeliYatra Status"
        digest_body = (
            "Kedarnath post-monsoon ticket booking has not opened yet.\n"
            f"Status: On hold.\n{TARGET_URL}"
        )
        send_ntfy_alert(digest_title, digest_body, priority="low")

        # Sends WhatsApp template
        send_meta_whatsapp_template()

    print("=" * 60)
    print("MONITOR RUN COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()

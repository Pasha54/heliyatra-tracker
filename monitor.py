"""
HeliYatra Post-Monsoon Watcher (Scrape.do + WhatsApp + ntfy.sh)
- Actively detects Kedarnath announcements, dates, and schedule updates.
- Sends the EXACT live announcement text directly to your notification.
- Stores page notice hash in a state file to alert on ANY website text change.
"""

import os
import re
import sys
import json
import hashlib
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

# State file to track content changes between runs
STATE_FILE = "heliyatra_notice_state.txt"

# Explicit triggers for booking openings & schedule announcements
OPENING_TRIGGERS = [
    r"september",
    r"october",
    r"11:00\s*am",
    r"booking\s+(will\s+)?open",
    r"booking\s+(is\s+)?open",
    r"slot[s]?\s+open",
    r"ticket\s+booking\s+schedule",
    r"phase",
]


def send_meta_whatsapp(message_text: str):
    """Sends WhatsApp notification via Meta Cloud API."""
    if not (WA_TOKEN and WA_PHONE_ID and WA_RECIPIENT):
        return False

    clean_recipient = WA_RECIPIENT.replace("+", "").replace(" ", "").replace("-", "").strip()
    url = f"https://graph.facebook.com/v20.0/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json"
    }

    # Attempt custom template first
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_recipient,
        "type": "template",
        "template": {
            "name": "heliyatra_update",
            "language": {"code": "en_US"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "HeliYatra Alert"[:50]},
                        {"type": "text", "text": message_text[:180]}
                    ]
                }
            ]
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code in [200, 201]:
            print(f"[WHATSAPP] Custom template delivered!")
            return True

        # Fallback to default hello_world ping
        fallback_payload = {
            "messaging_product": "whatsapp",
            "to": clean_recipient,
            "type": "template",
            "template": {"name": "hello_world", "language": {"code": "en_US"}}
        }
        f_resp = requests.post(url, headers=headers, json=fallback_payload, timeout=15)
        return f_resp.status_code in [200, 201]
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


def extract_portal_notices(soup: BeautifulSoup) -> list:
    """Extracts all visible banners, alerts, news, and marquee notices."""
    candidates = soup.find_all(
        lambda tag: tag.name in ["marquee", "div", "p", "span", "section", "li"] and (
            any(cls in " ".join(tag.get("class", [])).lower() for cls in ["alert", "notice", "news", "announcement", "banner", "marquee"])
            or any(word in tag.get_text().lower() for word in ["kedarnath", "september", "october", "booking", "schedule", "instructions"])
        )
    )

    notices = []
    for cand in candidates:
        text = cand.get_text(separator=" ", strip=True)
        # Filter out tiny buttons or giant full-page wraps
        if 20 < len(text) < 500 and text not in notices:
            # Skip pure Hemkund only notices
            if "hemkund" in text.lower() and "kedarnath" not in text.lower():
                continue
            notices.append(text)
    return notices


def main():
    print("=" * 60)
    print("STARTING HELIYATRA MONITOR RUN")
    print("=" * 60)

    html_content, status_code = fetch_via_scrapedo(SCRAPEDO_TOKEN)

    if not html_content or status_code != 200:
        print(f"[CRITICAL] Portal fetch failed with HTTP {status_code}.")
        send_ntfy_alert(
            "HeliYatra Check Notice",
            f"Portal check returned HTTP {status_code}. Retrying next run.\n{TARGET_URL}",
            priority="low"
        )
        return

    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    page_text = soup.get_text(separator=" ", strip=True)
    page_text_lower = page_text.lower()

    # Extract all relevant Kedarnath notices from the page
    notices = extract_portal_notices(soup)
    live_notice_summary = "\n\n".join(notices[:3]) if notices else page_text[:300]

    print(f"[INFO] Live Notice Summary Extracted:\n{live_notice_summary}\n")

    # 1. Check for specific opening triggers in Kedarnath context
    matched_triggers = [p for p in OPENING_TRIGGERS if re.search(p, page_text_lower)]
    print(f"[INFO] Matched Triggers: {matched_triggers}")

    # 2. Check if the portal notice has changed since the previous check
    current_hash = hashlib.sha256(live_notice_summary.encode("utf-8")).hexdigest()
    last_hash = ""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                last_hash = f.read().strip()
        except Exception:
            pass

    content_changed = bool(last_hash and current_hash != last_hash)
    print(f"[INFO] Content changed since last check: {content_changed}")

    # =========================================================================
    # ALERT LOGIC:
    # If triggers match OR the notice banner changed -> Send URGENT notification!
    # =========================================================================
    if matched_triggers or content_changed:
        print("🚨 URGENT: Booking announcement or schedule detected!")
        urgent_title = "🚨 URGENT: Kedarnath Heli Booking Announcement!"
        urgent_body = (
            f"Live Portal Notice:\n{live_notice_summary}\n\n"
            f"Tap to open & book: {TARGET_URL}"
        )
        send_ntfy_alert(urgent_title, urgent_body, priority="urgent")
        send_meta_whatsapp(f"URGENT: {live_notice_summary[:160]}")

    else:
        print("ℹ️ Routine Check: No new schedule changes.")
        send_ntfy_alert(
            "HeliYatra Check",
            f"Latest Notice:\n{live_notice_summary}\n\n{TARGET_URL}",
            priority="low"
        )
        send_meta_whatsapp(f"Latest Notice: {live_notice_summary[:160]}")

    # Save state
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(current_hash)
    except Exception as e:
        print(f"[WARN] Could not save state: {e}")

    print("=" * 60)
    print("MONITOR RUN COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()

"""
HeliYatra Post-Monsoon Watcher (Scrape.do + Official Meta WhatsApp Cloud API)
Includes detailed debug logs for WhatsApp API and Scrape.do responses.
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

# Optional fallback push
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "").strip()

# =========================================================================
# EXACT CURRENT BASELINE MESSAGE
# When IRCTC changes or removes this hold notice for Kedarnath,
# the script immediately detects the difference and fires an URGENT WhatsApp alert.
# =========================================================================
KNOWN_BASELINE_SNIPPET = "Shri Hemkund Sahib Helicopter ticket bookings are temporarily on hold till further instructions"


def send_meta_whatsapp(message_text: str):
    """Sends official WhatsApp message via Meta Cloud API with full debug logging."""
    print("-" * 50)
    print("[WHATSAPP] Preparing WhatsApp dispatch via Meta Graph API...")

    if not WA_TOKEN:
        print("[WHATSAPP ERROR] 'WA_TOKEN' is missing in environment variables!")
        return False
    if not WA_PHONE_ID:
        print("[WHATSAPP ERROR] 'WA_PHONE_ID' is missing in environment variables!")
        return False
    if not WA_RECIPIENT:
        print("[WHATSAPP ERROR] 'WA_RECIPIENT' is missing in environment variables!")
        return False

    clean_recipient = WA_RECIPIENT.replace("+", "").replace(" ", "").replace("-", "").strip()
    print(f"[WHATSAPP DEBUG] Sender Phone ID: {WA_PHONE_ID}")
    print(f"[WHATSAPP DEBUG] Recipient Number: {clean_recipient}")
    print(f"[WHATSAPP DEBUG] Token Preview: {WA_TOKEN[:8]}...{WA_TOKEN[-4:]}")

    url = f"https://graph.facebook.com/v20.0/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_recipient,
        "type": "text",
        "text": {
            "preview_url": True,
            "body": message_text
        }
    }

    try:
        print(f"[WHATSAPP DEBUG] POST -> {url}")
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        print(f"[WHATSAPP DEBUG] HTTP Status: {resp.status_code}")
        print(f"[WHATSAPP DEBUG] Response Body: {resp.text}")

        if resp.status_code in [200, 201]:
            print("[WHATSAPP SUCCESS] Message successfully delivered to WhatsApp queue!")
            return True
        else:
            print(f"[WHATSAPP FAILED] Meta returned error status {resp.status_code}.")
            try:
                err_data = resp.json()
                print(f"[WHATSAPP ERROR DETAILS] {json.dumps(err_data, indent=2)}")
            except Exception:
                pass
            return False
    except Exception as e:
        print(f"[WHATSAPP EXCEPTION] Failed to connect to Meta API: {e}")
        return False


def send_ntfy_fallback(title: str, message: str, priority: str = "low"):
    """Optional push backup to ntfy.sh"""
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
        resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=10)
        print(f"[NTFY DEBUG] Push status ({priority}): {resp.status_code}")
    except Exception as e:
        print(f"[NTFY ERROR] {e}")


def fetch_via_scrapedo(token: str):
    """Fetches portal HTML via Scrape.do with Indian IP proxy routing."""
    print("-" * 50)
    print("[SCRAPE.DO] Initiating fetch for HeliYatra portal...")

    if not token:
        print("[SCRAPE.DO ERROR] 'SCRAPEDO_TOKEN' is missing in environment variables!")
        return None, 401

    encoded_url = urllib.parse.quote(TARGET_URL, safe="")
    endpoint = f"https://api.scrape.do?token={token}&url={encoded_url}&geoCode=in"
    print(f"[SCRAPE.DO DEBUG] Token Preview: {token[:6]}... (Routing via India geoCode=in)")

    try:
        resp = requests.get(endpoint, timeout=60)
        print(f"[SCRAPE.DO DEBUG] HTTP Status: {resp.status_code}")
        print(f"[SCRAPE.DO DEBUG] Response Payload Length: {len(resp.text)} chars")
        return resp.text, resp.status_code
    except Exception as e:
        print(f"[SCRAPE.DO EXCEPTION] Fetch failed: {e}")
        return None, 500


def extract_visible_notice(soup: BeautifulSoup) -> str:
    """Finds marquee / alert banners on the page."""
    candidates = soup.find_all(
        lambda tag: tag.name in ["marquee", "div", "p", "span", "section"] and (
            any(cls in " ".join(tag.get("class", [])).lower() for cls in ["alert", "notice", "news", "announcement", "banner", "marquee"])
            or any(word in tag.get_text().lower() for word in ["hold", "booking", "monsoon", "instructions", "pilgrims", "kedarnath"])
        )
    )

    for cand in candidates:
        text = cand.get_text(separator=" ", strip=True)
        if 25 < len(text) < 400 and any(w in text.lower() for w in ["hold", "booking", "monsoon", "kedarnath", "instructions"]):
            return text

    all_text = soup.get_text(separator=" ", strip=True)
    lines = [line.strip() for line in all_text.split("  ") if len(line.strip()) > 15]
    return "\n".join(lines[:3]) if lines else "Site accessed successfully."


def main():
    print("=" * 60)
    print("STARTING HELIYATRA MONITOR RUN")
    print(f"Target URL: {TARGET_URL}")
    print("=" * 60)

    # 1. Fetch portal HTML
    html_content, status_code = fetch_via_scrapedo(SCRAPEDO_TOKEN)

    if not html_content or status_code != 200:
        print(f"[CRITICAL] Portal fetch failed with status code {status_code}.")
        send_meta_whatsapp(
            f"⚠️ HeliYatra Monitor Warning:\nPortal check returned HTTP {status_code}. Retrying on next hourly schedule."
        )
        return

    # 2. Parse HTML text
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    page_text = soup.get_text(separator=" ", strip=True)
    live_notice = extract_visible_notice(soup)

    print("-" * 50)
    print(f"[PARSER] Clean text extracted ({len(page_text)} chars).")
    print(f"[PARSER] Live Notice Banner:\n\"{live_notice}\"")

    # 3. Exact baseline snippet check
    print("-" * 50)
    print(f"[DIFF CHECK] Checking for exact known baseline snippet:\n\"{KNOWN_BASELINE_SNIPPET}\"")
    baseline_is_present = KNOWN_BASELINE_SNIPPET.lower() in page_text.lower()
    print(f"[DIFF CHECK RESULT] Baseline Present on Page: {baseline_is_present}")

    # 4. Trigger logic
    if not baseline_is_present:
        # BASELINE IS MISSING OR CHANGED -> BOOKING STATUS HAS CHANGED!
        print("=" * 60)
        print("🚨 TRIGGER: BASELINE CHANGED! SENDING URGENT WHATSAPP ALERT! 🚨")
        print("=" * 60)

        urgent_wa_msg = (
            "🚨 *URGENT: HELIYATRA PORTAL NOTICE CHANGED!* 🚨\n\n"
            "The previous hold message is no longer present on the website.\n"
            "Kedarnath post-monsoon ticket booking may be *OPEN* or updated!\n\n"
            f"📋 *Live Site Notice:*\n_{live_notice}_\n\n"
            f"👉 *Open & Book Now:* {TARGET_URL}"
        )
        send_meta_whatsapp(urgent_wa_msg)
        send_ntfy_fallback("URGENT: HeliYatra Booking Might Be OPEN!", live_notice, priority="urgent")

    else:
        # BASELINE IS STILL PRESENT -> HOURLY DIGEST
        print("-" * 50)
        print("[DIGEST] Baseline message still active on site. Sending hourly WhatsApp digest.")
        
        digest_wa_msg = (
            "🚁 *HeliYatra Status Digest*\n\n"
            "✅ *Status:* Monsoon hold active (No changes detected).\n\n"
            f"📋 *Current Site Notice:*\n_{live_notice[:250]}_\n\n"
            "⏳ Next check in 1 hour."
        )
        send_meta_whatsapp(digest_wa_msg)
        send_ntfy_fallback("HeliYatra Hourly Digest", live_notice, priority="low")

    print("=" * 60)
    print("MONITOR RUN COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()

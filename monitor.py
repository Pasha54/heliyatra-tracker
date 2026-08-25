"""
HeliYatra Post-Monsoon Cron Watcher (CloudFront Bypass with ScraperAPI)
Runs on GitHub Actions every 6 hours and pushes notifications to ntfy.sh
"""

import os
import sys
import requests
from bs4 import BeautifulSoup

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "heliyatra_postmonsoon_alert_2026")
TARGET_URL = "https://heliyatra.irctc.co.in"
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "").strip()

KEYWORDS = [
    "post monsoon",
    "post-monsoon",
    "booking open",
    "ticket booking",
    "september",
    "october",
    "slot open",
    "kedarnath"
]

def send_alert(title, message, priority="low"):
    """Sends notification to ntfy.sh with clean ASCII headers."""
    try:
        clean_title = title.encode("ascii", "ignore").decode("ascii").strip() or "HeliYatra Alert"
        url = f"https://ntfy.sh/{NTFY_TOPIC}"
        headers = {
            "Title": clean_title,
            "Priority": priority,
            "Click": TARGET_URL,
        }
        resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=15)
        print(f"[NTFY] Push status: {resp.status_code}")
    except Exception as e:
        print(f"[NTFY ERROR] {e}")


def fetch_page():
    """Fetches the target page via ScraperAPI residential node."""
    if not SCRAPER_API_KEY:
        print("[ERROR] SCRAPER_API_KEY is not found in environment!")
        return None, 401

    print(f"[INFO] Fetching via ScraperAPI (Key: {SCRAPER_API_KEY[:4]}***)...")
    proxy_url = f"https://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={TARGET_URL}&country_code=in"
    
    resp = requests.get(proxy_url, timeout=60)
    print(f"[INFO] ScraperAPI HTTP Status: {resp.status_code}")
    return resp.text, resp.status_code


def main():
    print("=" * 60)
    print(f"Checking HeliYatra: {TARGET_URL}")
    print("=" * 60)

    html_content, status_code = fetch_page()

    if not html_content or status_code != 200:
        print(f"[CRITICAL] Fetch failed with status: {status_code}")
        send_alert(
            "HeliYatra 6h Check Notice",
            f"Portal check returned status {status_code}.\n"
            f"SCRAPER_API_KEY provided: {'YES' if SCRAPER_API_KEY else 'NO'}\n"
            f"Next automated check will retry in 6 hours.",
            priority="low"
        )
        return

    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    page_text = soup.get_text(separator=" ", strip=True)
    page_text_lower = page_text.lower()

    # Search for post-monsoon booking triggers
    matched = [k for k in KEYWORDS if k in page_text_lower]

    lines = [line.strip() for line in page_text.split("  ") if len(line.strip()) > 15]
    live_notice = "\n".join(lines[:4]) if lines else "Site accessed successfully."

    print(f"[SUCCESS] Page loaded! Text length: {len(page_text)} characters.")

    if matched:
        print(f"[TRIGGER] Post-monsoon keywords detected: {matched}")
        send_alert(
            "URGENT: HeliYatra Booking Trigger!",
            f"Keywords detected: {', '.join(matched)}\n\n"
            f"Live Notice:\n{live_notice[:350]}\n\n"
            f"Tap to open heliyatra.irctc.co.in now!",
            priority="urgent"
        )
    else:
        print("[DIGEST] No post-monsoon keywords yet. Sending 6-hour digest.")
        send_alert(
            "HeliYatra 6h Status Digest",
            f"Current Notice on Site:\n{live_notice[:350]}\n\n"
            f"Status: Monsoon hold still active (Booking closed).",
            priority="low"
        )


if __name__ == "__main__":
    main()

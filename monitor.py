"""
HeliYatra Post-Monsoon Cron Watcher (CloudFront 403 Bypass)
Runs on GitHub Actions every 6 hours and pushes notifications to ntfy.sh
"""

import os
import sys
import time
import random
import urllib.request
import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "heliyatra_postmonsoon_alert_2026")
TARGET_URL = "https://heliyatra.irctc.co.in"
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "")

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


def fetch_via_scraperapi(key):
    """Bypasses CloudFront WAF using free ScraperAPI Indian exit nodes."""
    print("[INFO] Attempting fetch via ScraperAPI (India node)...")
    proxy_url = f"https://api.scraperapi.com?api_key={key}&url={TARGET_URL}&country_code=in"
    resp = requests.get(proxy_url, timeout=35)
    return resp.text, resp.status_code


def fetch_via_indian_proxy():
    """Fetches public Indian HTTP proxies and tries connecting through them."""
    print("[INFO] Fetching free Indian proxy list...")
    try:
        list_url = "https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&country=IN&protocol=http&timeout=7000&proxy_format=ipport"
        req = urllib.request.Request(list_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            proxies = [p.strip() for p in r.read().decode("utf-8").splitlines() if ":" in p]
    except Exception as e:
        print(f"[WARN] Could not load proxy list: {e}")
        proxies = []

    for proxy in proxies[:4]:
        try:
            print(f"[INFO] Testing Indian proxy {proxy}...")
            resp = requests.get(
                TARGET_URL,
                proxies={"http": f"http://{proxy}", "https": f"http://{proxy}"},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.text, 200
        except Exception:
            continue
    return None, 403


def fetch_page():
    """Attempts direct Chrome impersonation -> ScraperAPI -> Free Indian Proxy."""
    # 1. Try direct Chrome TLS
    try:
        print("[INFO] Trying direct Chrome TLS impersonation...")
        resp = cffi_requests.get(TARGET_URL, impersonate="chrome120", timeout=20)
        if resp.status_code == 200:
            return resp.text, 200
        print(f"[WARN] Direct access returned HTTP {resp.status_code} (CloudFront geo-block).")
    except Exception as e:
        print(f"[WARN] Direct access error: {e}")

    # 2. Try ScraperAPI if key is present
    if SCRAPER_API_KEY:
        try:
            return fetch_via_scraperapi(SCRAPER_API_KEY)
        except Exception as e:
            print(f"[WARN] ScraperAPI failed: {e}")

    # 3. Fallback to free Indian proxies
    return fetch_via_indian_proxy()


def main():
    print("=" * 60)
    print(f"Checking HeliYatra: {TARGET_URL}")
    print("=" * 60)

    html_content, status_code = fetch_page()

    if not html_content or status_code != 200:
        print(f"[CRITICAL] Portal returned HTTP {status_code}.")
        send_alert(
            "HeliYatra 6h Check Notice",
            f"Portal check returned HTTP {status_code} (CloudFront protected).\n"
            f"If persistent, add a free SCRAPER_API_KEY in GitHub Secrets.\n"
            f"Next automated check will run in 6 hours.",
            priority="low"
        )
        return

    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    page_text = soup.get_text(separator=" ", strip=True)
    page_text_lower = page_text.lower()

    # Search for keywords
    matched = [k for k in KEYWORDS if k in page_text_lower]

    lines = [line.strip() for line in page_text.split("  ") if len(line.strip()) > 15]
    live_notice = "\n".join(lines[:4]) if lines else "Site accessed successfully."

    print(f"[SUCCESS] Page loaded! Length: {len(page_text)} chars")

    if matched:
        print(f"[TRIGGER] Post-monsoon keywords found: {matched}")
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

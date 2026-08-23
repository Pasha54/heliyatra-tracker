"""
HeliYatra Post-Monsoon & IRCTC Web Cron Monitor
Runs automatically on GitHub Actions / Cloud Cron every 6 hours.

DUAL-TIER ALERT SYSTEM:
1. HIGH / URGENT PRIORITY: Triggered immediately if post-monsoon keywords
   are detected or the notice changes.
2. LOW PRIORITY 6-HOUR DIGEST: Sent on every run with the current notice.
"""

import os
import sys
import time
import random
import hashlib
from datetime import datetime, timezone

# High-Performance Anti-Bot TLS Library
try:
    from curl_cffi import requests
    USE_CURL_CFFI = True
except ImportError:
    import requests
    USE_CURL_CFFI = False

from bs4 import BeautifulSoup

# ==========================================
# CONFIGURATION
# ==========================================
TARGET_URL = "https://heliyatra.irctc.co.in"
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "heliyatra_postmonsoon_alert_2026")
HIGH_PRIORITY = "urgent"   # Loud siren/vibration for actual booking triggers
LOW_PRIORITY = "low"       # Silent/gentle notification for 6-hour status digests
KEYWORDS_TO_WATCH = [
    "post monsoon",
    "post-monsoon",
    "booking open",
    "ticket booking open",
    "september",
    "october",
    "slot open",
    "kedarnath booking",
    "shri kedarnath dham",
    "helicopter ticket",
    "irctc ticket"
]
STATE_FILE = "last_state_hash.txt"

# Anti-Bot Browser Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def send_ntfy_alert(title: str, message: str, priority: str = "default", tags: list = None, click_url: str = TARGET_URL):
    """Sends a push notification to your phone/desktop via ntfy.sh (ASCII-safe headers)"""
    if not NTFY_TOPIC or NTFY_TOPIC.startswith("your_"):
        print("[WARNING] NTFY_TOPIC is not set. Notification skipped.")
        return

    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    tag_str = ",".join(tags or ["helicopter", "bell"])
    
    # Strip any unicode from headers to prevent latin-1 HTTP header encoding crashes
    clean_title = title.encode("ascii", "ignore").decode("ascii").strip()
    if not clean_title:
        clean_title = "HeliYatra IRCTC Alert"

    headers = {
        "Title": clean_title,
        "Priority": priority,
        "Tags": tag_str,
        "Click": click_url,
    }

    try:
        import requests as std_requests
        resp = std_requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=15)
        if resp.status_code == 200:
            print(f"[SUCCESS] Delivered [{priority.upper()}] notification to ntfy.sh/{NTFY_TOPIC}")
        else:
            print(f"[ERROR] Failed to send notification: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[EXCEPTION] Failed to dispatch ntfy alert: {e}")


def get_last_hash() -> str:
    """Reads previous SHA-256 hash of the page content if cached."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""
    return ""


def save_current_hash(content_hash: str):
    """Saves current SHA-256 hash to disk for diffing against subsequent runs."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(content_hash)
    except Exception as e:
        print(f"[WARNING] Could not write state file: {e}")


def fetch_page_with_retry(url: str, max_retries: int = 3):
    """Fetches the target URL with curl_cffi Chrome impersonation to bypass CloudFront WAF."""
    jitter = random.uniform(1.2, 3.5)
    print(f"[INFO] Applying {jitter:.2f}s anti-bot jitter delay...")
    time.sleep(jitter)

    impersonate_targets = ["chrome124", "chrome120", "safari15_5"]

    for attempt in range(1, max_retries + 1):
        target_imp = impersonate_targets[(attempt - 1) % len(impersonate_targets)]
        try:
            print(f"[INFO] Fetching {url} (Attempt {attempt}/{max_retries}, Profile: {target_imp})...")
            if USE_CURL_CFFI:
                session = requests.Session(impersonate=target_imp)
                response = session.get(url, headers=HEADERS, timeout=30)
            else:
                response = requests.get(url, headers=HEADERS, timeout=30)
            
            if response.status_code == 200:
                return response.text, response.status_code, None
            elif response.status_code == 403:
                print(f"[WARN] 403 Forbidden on attempt {attempt}. Retrying with next cipher profile...")
                time.sleep(3 * attempt)
            else:
                print(f"[WARN] HTTP Status {response.status_code}. Retrying...")
                time.sleep(2 * attempt)
                
        except Exception as e:
            print(f"[ERROR] Request failed on attempt {attempt}: {e}")
            if attempt == max_retries:
                return None, None, str(e)
            time.sleep(3 * attempt)

    return None, 403, "CloudFront/WAF blocked or timeout reached"


def extract_key_notice(soup: BeautifulSoup) -> str:
    """Extracts the prominent notice / banner text from the page for the digest."""
    notice_candidates = soup.find_all(
        lambda tag: tag.name in ["marquee", "div", "p", "span", "section"] and (
            any(cls in " ".join(tag.get("class", [])).lower() for cls in ["alert", "notice", "news", "announcement", "banner", "marquee", "hold"])
            or any(word in tag.get_text().lower() for word in ["hold", "temporarily", "booking", "monsoon", "instructions", "pilgrims"])
        )
    )

    for cand in notice_candidates:
        text = cand.get_text(separator=" ", strip=True)
        if 20 < len(text) < 400 and any(w in text.lower() for w in ["hold", "booking", "monsoon", "kedarnath", "shri"]):
            return text

    all_text = soup.get_text(separator=" ", strip=True)
    clean_lines = [line.strip() for line in all_text.split("  ") if len(line.strip()) > 15]
    if clean_lines:
        return " | ".join(clean_lines[:3])[:300]

    return "Shri Kedarnath Dham helicopter booking portal"


def main():
    utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print("=" * 65)
    print(f"HeliYatra IRCTC Monitor Check: {utc_now}")
    print(f"Target: {TARGET_URL}")
    print(f"TLS Engine: {'curl_cffi (Chrome Impersonation)' if USE_CURL_CFFI else 'Standard Requests'}")
    print("=" * 65)

    html_content, status_code, fetch_error = fetch_page_with_retry(TARGET_URL)

    # -------------------------------------------------------------
    # CASE 1: FETCH FAILED -> SEND LOW-PRIORITY WARNING DIGEST
    # -------------------------------------------------------------
    if not html_content:
        print(f"[CRITICAL] Could not fetch page. Status: {status_code}, Error: {fetch_error}")
        send_ntfy_alert(
            title="HeliYatra Portal Fetch Notice",
            message=(
                f"Status: HTTP {status_code or 'Timeout'}\n"
                f"Note: CloudFront rate-limited this run.\n"
                f"Time: {utc_now}\n\n"
                f"The scheduled cron check could not reach heliyatra.irctc.co.in. "
                f"Next automated check will retry in 6 hours."
            ),
            priority=LOW_PRIORITY,
            tags=["warning", "satellite"],
            click_url=TARGET_URL
        )
        return

    # Parse HTML
    soup = BeautifulSoup(html_content, "html.parser")
    for element in soup(["script", "style", "noscript", "svg"]):
        element.extract()

    page_text = soup.get_text(separator=" ", strip=True)
    current_hash = hashlib.sha256(page_text.encode("utf-8")).hexdigest()
    last_hash = get_last_hash()
    
    live_notice_text = extract_key_notice(soup)

    print(f"[INFO] Page text length: {len(page_text)} chars | Hash: {current_hash[:12]}...")
    print(f"[INFO] Live Notice on Site: \"{live_notice_text[:120]}...\"")

    # Check for monitored keywords
    matched_keywords = []
    page_text_lower = page_text.lower()
    for kw in KEYWORDS_TO_WATCH:
        if kw.lower() in page_text_lower:
            matched_keywords.append(kw)

    content_changed = bool(last_hash and current_hash != last_hash)

    # -------------------------------------------------------------
    # CASE 2: HIGH PRIORITY TRIGGER (Keywords found OR Content changed)
    # -------------------------------------------------------------
    if matched_keywords or content_changed:
        print(f"[TRIGGER] High Priority Alert! Keywords: {matched_keywords} | Changed: {content_changed}")
        
        if matched_keywords:
            alert_title = "URGENT: HeliYatra Post-Monsoon Booking Trigger!"
            alert_body = (
                f"Keywords Found: {', '.join(matched_keywords)}\n\n"
                f"Current Site Notice:\n\"{live_notice_text}\"\n\n"
                f"Post-monsoon Kedarnath booking may be LIVE! Tap to open heliyatra.irctc.co.in right now!"
            )
        else:
            alert_title = "HeliYatra Notice Banner Updated!"
            alert_body = (
                f"The notice banner on HeliYatra IRCTC has just updated!\n\n"
                f"New Site Notice:\n\"{live_notice_text}\"\n\n"
                f"Tap to check for new post-monsoon advisory dates."
            )

        send_ntfy_alert(
            title=alert_title,
            message=alert_body,
            priority=HIGH_PRIORITY,
            tags=["rotating_light", "helicopter", "rocket", "warning"],
            click_url=TARGET_URL
        )

    # -------------------------------------------------------------
    # CASE 3: LOW PRIORITY 6-HOUR DIGEST (Always informs you of current status)
    # -------------------------------------------------------------
    else:
        print("[DIGEST] Sending 6-hour status notification with current site message...")
        send_ntfy_alert(
            title="HeliYatra 6h Status Check",
            message=(
                f"Current Message on Site:\n\"{live_notice_text}\"\n\n"
                f"Status: Monsoon hold still active (No post-monsoon keywords yet).\n"
                f"Checked: {utc_now}"
            ),
            priority=LOW_PRIORITY,
            tags=["helicopter", "information_source", "hourglass"],
            click_url=TARGET_URL
        )

    save_current_hash(current_hash)


if __name__ == "__main__":
    main()

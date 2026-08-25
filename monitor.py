"""
HeliYatra Post-Monsoon Watcher via Scrape.do
Methodology: Strict Baseline String Matching.
If the known baseline status message changes in ANY way, trigger URGENT alert.
Otherwise, send the silent 2-hour status digest.
"""

import os
import sys
import urllib.parse
import requests
from bs4 import BeautifulSoup

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "heliyatra_postmonsoon_alert_2026")
TARGET_URL = "https://heliyatra.irctc.co.in"
SCRAPEDO_TOKEN = os.getenv("SCRAPEDO_TOKEN", "").strip()

# =========================================================================
# EXACT CURRENT BASELINE MESSAGE
# As long as this exact sentence / state is present, booking is NOT open.
# When IRCTC updates the page for Kedarnath Post-Monsoon, this match will fail
# and immediately trigger an URGENT alert!
# =========================================================================
KNOWN_BASELINE_SNIPPET = "Shri Hemkund Sahib Helicopter ticket bookings are temporarily on hold till further instructions"


def send_alert(title: str, message: str, priority: str = "low"):
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
        print(f"[NTFY] Notification pushed ({priority.upper()}): HTTP {resp.status_code}")
    except Exception as e:
        print(f"[NTFY ERROR] {e}")


def fetch_via_scrapedo(token: str):
    """Fetches target page through Scrape.do with Indian geo-routing."""
    if not token:
        print("[ERROR] SCRAPEDO_TOKEN not found in environment!")
        return None, 401

    print(f"[INFO] Fetching {TARGET_URL} via Scrape.do (Token: {token[:4]}***)...")
    encoded_url = urllib.parse.quote(TARGET_URL, safe="")
    # Scrape.do API endpoint
    endpoint = f"https://api.scrape.do?token={token}&url={encoded_url}&geoCode=in"

    resp = requests.get(endpoint, timeout=60)
    print(f"[INFO] Scrape.do HTTP Response: {resp.status_code}")
    return resp.text, resp.status_code


def extract_visible_notice(soup: BeautifulSoup) -> str:
    """Extracts the live notice text from the page for the digest."""
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
    print(f"Checking HeliYatra: {TARGET_URL}")
    print("=" * 60)

    html_content, status_code = fetch_via_scrapedo(SCRAPEDO_TOKEN)

    if not html_content or status_code != 200:
        print(f"[CRITICAL] Portal check failed with status: {status_code}")
        send_alert(
            "HeliYatra Check Notice",
            f"Portal check returned status {status_code}.\n"
            f"SCRAPEDO_TOKEN in env: {'YES' if SCRAPEDO_TOKEN else 'NO'}\n"
            f"Next automated check will retry in 2 hours.",
            priority="low"
        )
        return

    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    page_text = soup.get_text(separator=" ", strip=True)
    live_notice = extract_visible_notice(soup)

    print(f"[SUCCESS] Page loaded successfully! Text length: {len(page_text)} chars.")
    print(f"[INFO] Current Visible Notice:\n\"{live_notice}\"")

    # =========================================================================
    # BASELINE EXACT CHECK:
    # Does the page still have the exact known baseline text?
    # =========================================================================
    baseline_is_present = KNOWN_BASELINE_SNIPPET.lower() in page_text.lower()
    print(f"[CHECK] Known Baseline Present: {baseline_is_present}")

    if not baseline_is_present:
        # The baseline snippet is GONE or CHANGED -> Booking might be OPEN or Schedule Updated!
        print("[TRIGGER] Baseline snippet CHANGED or REMOVED! Dispatching URGENT alert.")
        send_alert(
            "URGENT: HeliYatra Portal Changed / Booking Might Be OPEN!",
            f"The previous hold notice has CHANGED on the website!\n\n"
            f"Current Site Notice:\n\"{live_notice}\"\n\n"
            f"Post-monsoon Kedarnath booking may be LIVE! Tap to open portal now.",
            priority="urgent"
        )
    else:
        # Exact same baseline -> Booking is still closed, send normal 6h digest
        print("[DIGEST] Baseline message still active. Sending 6-hour digest.")
        send_alert(
            "HeliYatra 6h Status Digest",
            f"Current Notice on Site:\n\"{live_notice}\"\n\n"
            f"Status: Monsoon hold still active (No change on portal).\n"
            f"Next check in 2 hours.",
            priority="low"
        )


if __name__ == "__main__":
    main()

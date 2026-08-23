import os
import time
import random
import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

# Put your preferred topic name here:
NTFY_TOPIC = "heliyatra_postmonsoon_alert_2026"
TARGET_URL = "https://heliyatra.irctc.co.in"

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
    """Sends notification to ntfy.sh without any emoji in headers to prevent latin-1 crashes."""
    try:
        url = f"https://ntfy.sh/{NTFY_TOPIC}"
        headers = {
            "Title": title,
            "Priority": priority,
            "Click": TARGET_URL,
        }
        resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=15)
        print(f"NTFY response: {resp.status_code}")
    except Exception as e:
        print(f"Failed to send to ntfy: {e}")

def main():
    print(f"Checking {TARGET_URL} with Chrome impersonation...")
    time.sleep(random.uniform(1.0, 2.5))
    
    try:
        # Uses real Chrome TLS handshake to bypass CloudFront WAF
        resp = cffi_requests.get(TARGET_URL, impersonate="chrome120", timeout=25)
        print(f"HTTP Status: {resp.status_code}")
        
        if resp.status_code != 200:
            send_alert("HeliYatra Check Notice", f"HTTP Status {resp.status_code} received when accessing portal.", priority="low")
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        page_text = soup.get_text(separator=" ", strip=True)
        page_text_lower = page_text.lower()
        
        # Look for keywords
        matched = [k for k in KEYWORDS if k in page_text_lower]
        
        # Get a readable preview of the notice banner
        lines = [line.strip() for line in page_text.split("  ") if len(line.strip()) > 20]
        preview_text = "\n".join(lines[:4]) if lines else "Site accessed successfully."

        if matched:
            print(f"KEYWORDS DETECTED: {matched}")
            send_alert(
                "URGENT: HeliYatra Booking Trigger",
                f"Matched keywords: {', '.join(matched)}\n\nNotice:\n{preview_text[:350]}\n\nTap to open portal now!",
                priority="urgent"
            )
        else:
            print("No new post-monsoon keywords. Sending 6-hour digest.")
            send_alert(
                "HeliYatra 6h Status Digest",
                f"Current Site Notice:\n{preview_text[:350]}\n\nStatus: Monsoon hold still active.",
                priority="low"
            )

    except Exception as e:
        print(f"Scraper error: {e}")
        send_alert("HeliYatra Fetch Error", f"Error accessing site: {e}", priority="low")

if __name__ == "__main__":
    main()

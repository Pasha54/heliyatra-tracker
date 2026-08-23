import os, time, random, requests
from bs4 import BeautifulSoup

# Choose your own private topic name
NTFY_TOPIC = "heliyatra_postmonsoon_alert_2026"
TARGET_URL = "https://heliyatra.irctc.co.in"
KEYWORDS = ["Post Monsoon", "Post-Monsoon", "Booking Open", "Kedarnath", "September"]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def main():
    time.sleep(random.uniform(1.5, 3.5))  # Anti-bot jitter delay
    resp = requests.get(TARGET_URL, headers=headers, timeout=25)
    
    if resp.status_code != 200:
        print(f"Failed to fetch: {resp.status_code}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    page_text = soup.get_text().lower()

    matches = [kw for kw in KEYWORDS if kw.lower() in page_text]

    if matches:
        print(f"Keywords detected: {matches}")
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=f"HeliYatra Post-Monsoon Booking may be OPEN! Detected: {', '.join(matches)}".encode("utf-8"),
            headers={
                "Title": "🚨 HeliYatra Post-Monsoon Alert!",
                "Priority": "urgent",
                "Tags": "helicopter,warning",
                "Click": TARGET_URL
            }
        )
    else:
        print("Booking still closed. No notification sent.")

if __name__ == "__main__":
    main()

import re
import time
from datetime import datetime

import requests

NBA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.nba.com/",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}


def safe_get(url, headers=None, timeout=15, retries=3):
    """GET with exponential backoff. Returns Response or None."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            return resp
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def slugify(name):
    """Lowercase, spaces to hyphens, strip apostrophes and dots."""
    name = name.lower()
    name = name.replace("'", "").replace(".", "")
    name = re.sub(r"\s+", "-", name.strip())
    name = re.sub(r"[^a-z0-9-]", "", name)
    return name


def log(msg):
    """Print with timestamp."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

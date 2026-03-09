"""Fetch headshots for historical/retired NBA players using nba_api package."""

import json
import os
import re
import time
import urllib.request

try:
    from nba_api.stats.endpoints import commonallplayers
    from nba_api.stats.library.parameters import Season
    USE_NBA_API = True
except ImportError:
    USE_NBA_API = False

ORIGINAL_DIR = os.path.join("players", "headshots", "original")
META_DIR = os.path.join("players", "metadata")
CDN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def slugify(name):
    """Lowercase, spaces to hyphens, strip apostrophes and dots."""
    name = name.lower()
    name = name.replace("'", "").replace(".", "")
    name = re.sub(r"\s+", "-", name.strip())
    name = re.sub(r"[^a-z0-9-]", "", name)
    return name


def get_historical_players():
    """Fetch all players from nba_api and filter to post-1970 era."""
    print("[info] Fetching all players from nba_api...")
    all_players = commonallplayers.CommonAllPlayers(
        is_only_current_season=0,
        league_id='00',
        season='2024-25'
    )
    df = all_players.get_data_frames()[0]

    # Filter to players from 1970 onwards (era with likely photos)
    df = df[df["FROM_YEAR"].astype(int) >= 1970]

    players = []
    for _, row in df.iterrows():
        nba_id = int(row["PERSON_ID"])
        # DISPLAY_LAST_COMMA_FIRST is "Last, First" — convert to "First Last"
        display = row["DISPLAY_LAST_COMMA_FIRST"]
        if "," in display:
            last, first = display.split(",", 1)
            full_name = f"{first.strip()} {last.strip()}"
        else:
            full_name = display.strip()
        slug = slugify(full_name)
        players.append((nba_id, slug))

    print(f"[info] Found {len(players)} players from 1970 onwards")
    return players


def download_headshot(nba_id, slug):
    """Download a single headshot from the NBA CDN."""
    out_path = os.path.join(ORIGINAL_DIR, f"{nba_id}-{slug}.png")
    if os.path.exists(out_path):
        return "skip"

    url = f"https://cdn.nba.com/headshots/nba/latest/1040x760/{nba_id}.png"
    try:
        req = urllib.request.Request(url, headers=CDN_HEADERS)
        resp = urllib.request.urlopen(req, timeout=10)
        content = resp.read()
        if resp.status == 200 and len(content) > 15000:
            with open(out_path, "wb") as f:
                f.write(content)
            return "ok"
        else:
            return "404"
    except Exception:
        return "404"


if __name__ == "__main__":
    if not USE_NBA_API:
        print("ERROR: nba_api package is not installed.")
        print("Install it with: py -m pip install nba_api")
        exit(1)

    os.makedirs(ORIGINAL_DIR, exist_ok=True)
    os.makedirs(META_DIR, exist_ok=True)

    players = get_historical_players()

    downloaded = 0
    skipped = 0
    not_found = 0
    downloaded_players = []

    total = len(players)
    for i, (nba_id, slug) in enumerate(players):
        result = download_headshot(nba_id, slug)
        if result == "ok":
            print(f"OK   {nba_id}-{slug}")
            downloaded += 1
            downloaded_players.append({"nba_id": nba_id, "slug": slug})
        elif result == "skip":
            print(f"SKIP {nba_id}-{slug}")
            skipped += 1
        else:
            print(f"404  {nba_id}-{slug}")
            not_found += 1

        if (i + 1) % 100 == 0:
            print(f"[progress] {i + 1}/{total} — downloaded:{downloaded} skipped:{skipped} 404:{not_found}")

        time.sleep(0.2)

    print(f"\nDone. Downloaded: {downloaded}, Already existed: {skipped}, 404: {not_found}")

    results = {
        "total_attempted": total,
        "downloaded": downloaded,
        "skipped": skipped,
        "not_found": not_found,
        "downloaded_players": downloaded_players,
    }
    results_path = os.path.join(META_DIR, "historical_results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote results to {results_path}")

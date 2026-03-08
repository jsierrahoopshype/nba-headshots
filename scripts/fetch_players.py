"""Download NBA player headshots from the NBA CDN."""

import argparse
import json
import os
import time

from utils import STATIC_CDN_HEADERS, log, safe_get

PLAYER_INDEX_URL = "https://cdn.nba.com/static/json/staticData/playerIndex.json"
HEADSHOT_URL = "https://cdn.nba.com/headshots/nba/latest/1040x760/{nba_id}.png"
ORIGINAL_DIR = os.path.join("players", "headshots", "original")
METADATA_DIR = os.path.join("players", "metadata")


def fetch_player_list():
    log("Fetching player index from NBA static CDN...")
    resp = safe_get(PLAYER_INDEX_URL, headers=STATIC_CDN_HEADERS, timeout=30)
    if not resp or resp.status_code != 200:
        log("ERROR: Failed to fetch player index")
        return []

    data = resp.json()
    rows = data["players"]

    players = []
    for row in rows:
        person_id = row[2]
        first_name = row[1]
        last_name = row[0]
        team_id = row[4]
        team_abbrev = row[7]
        is_active = row[21]

        players.append({
            "nba_id": person_id,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": f"{first_name} {last_name}",
            "from_year": None,
            "to_year": None,
            "roster_status": 1 if is_active == 1 else 0,
            "team_id": team_id,
            "team_abbrev": team_abbrev,
        })

    log(f"Found {len(players)} players")
    return players


def download_headshots(players, limit=None):
    os.makedirs(ORIGINAL_DIR, exist_ok=True)
    os.makedirs(METADATA_DIR, exist_ok=True)

    if limit:
        players = players[:limit]

    missing = []
    downloaded = 0
    skipped = 0

    for i, p in enumerate(players):
        nba_id = p["nba_id"]
        out_path = os.path.join(ORIGINAL_DIR, f"{nba_id}.png")

        if os.path.exists(out_path):
            skipped += 1
            continue

        url = HEADSHOT_URL.format(nba_id=nba_id)
        resp = safe_get(url, timeout=15)

        if resp and resp.status_code == 200 and len(resp.content) > 5000:
            with open(out_path, "wb") as f:
                f.write(resp.content)
            downloaded += 1
        else:
            missing.append({
                "nba_id": nba_id,
                "full_name": p["full_name"],
                "from_year": p["from_year"],
                "to_year": p["to_year"],
                "tried_sources": ["nba_cdn"],
            })

        if (i + 1) % 100 == 0:
            log(f"Progress: {i + 1}/{len(players)} | downloaded={downloaded} skipped={skipped} missing={len(missing)}")

        time.sleep(0.25)

    log(f"Done. downloaded={downloaded} skipped={skipped} missing={len(missing)}")

    missing_path = os.path.join(METADATA_DIR, "missing.json")
    with open(missing_path, "w") as f:
        json.dump(missing, f, indent=2)
    log(f"Wrote {missing_path} ({len(missing)} entries)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download NBA player headshots")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of players (for testing)")
    args = parser.parse_args()

    players = fetch_player_list()
    if players:
        download_headshots(players, limit=args.limit)

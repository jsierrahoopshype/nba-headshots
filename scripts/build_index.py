"""Build the master player and team JSON indexes."""

import json
import os
import urllib.request
from datetime import datetime, timezone

from utils import log, slugify

PLAYER_INDEX_URL = "https://cdn.nba.com/static/json/staticData/playerIndex.json"
FACE_DIR = os.path.join("players", "headshots", "face")
ORIGINAL_DIR = os.path.join("players", "headshots", "original")
METADATA_DIR = os.path.join("players", "metadata")

HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_player_list():
    log("Fetching player index from NBA CDN...")
    try:
        req = urllib.request.Request(PLAYER_INDEX_URL, headers=HEADERS)
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    except Exception as e:
        log(f"ERROR: Failed to fetch player index: {type(e).__name__}: {e}")
        return []

    result_set = data["resultSets"][0]
    headers = result_set["headers"]
    rows = result_set["rowSet"]

    ID = headers.index("PERSON_ID")
    FIRST = headers.index("PLAYER_FIRST_NAME")
    LAST = headers.index("PLAYER_LAST_NAME")
    TEAM_ID = headers.index("TEAM_ID")
    TEAM_ABB = headers.index("TEAM_ABBREVIATION")
    STATUS = headers.index("ROSTER_STATUS")

    players = []
    for row in rows:
        players.append({
            "nba_id": row[ID],
            "first_name": row[FIRST],
            "last_name": row[LAST],
            "full_name": f"{row[FIRST]} {row[LAST]}",
            "from_year": row[headers.index("FROM_YEAR")] if "FROM_YEAR" in headers else None,
            "to_year": row[headers.index("TO_YEAR")] if "TO_YEAR" in headers else None,
            "roster_status": row[STATUS],
            "team_id": row[TEAM_ID],
            "team_abbrev": row[TEAM_ABB],
        })
    return players


def build_index():
    players = fetch_player_list()
    if not players:
        return

    # Load ESPN crosswalk if available
    crosswalk = {}
    crosswalk_path = os.path.join(METADATA_DIR, "espn_crosswalk.json")
    if os.path.exists(crosswalk_path):
        with open(crosswalk_path) as f:
            crosswalk = json.load(f)
        log(f"Loaded ESPN crosswalk ({len(crosswalk)} entries)")

    records = []
    with_headshot = 0

    for p in players:
        nba_id = p["nba_id"]
        slug = slugify(p["full_name"])
        filename = f"{nba_id}-{slug}.png"
        has_face = os.path.exists(os.path.join(FACE_DIR, filename))
        has_original = os.path.exists(os.path.join(ORIGINAL_DIR, filename))
        espn_id = crosswalk.get(str(nba_id))

        if has_face:
            with_headshot += 1

        source = "nba_cdn"
        if espn_id:
            source = "espn"

        record = {
            "nba_id": nba_id,
            "full_name": p["full_name"],
            "first_name": p["first_name"],
            "last_name": p["last_name"],
            "slug": slug,
            "team_id": p["team_id"],
            "team_abbrev": p["team_abbrev"],
            "active": p["roster_status"] == 1,
            "seasons_from": p["from_year"],
            "seasons_to": p["to_year"],
            "headshot": {
                "face": has_face,
                "original": has_original,
                "source": source,
                "filename": filename,
            },
        }
        if espn_id:
            record["espn_id"] = int(espn_id)

        records.append(record)

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_players": len(records),
        "with_headshot": with_headshot,
        "players": records,
    }

    os.makedirs(METADATA_DIR, exist_ok=True)

    # Full index
    index_path = os.path.join(METADATA_DIR, "players.json")
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    log(f"Wrote {index_path}")

    # Active only
    active_records = [r for r in records if r["active"]]
    active_index = {
        "generated_at": index["generated_at"],
        "total_players": len(active_records),
        "with_headshot": sum(1 for r in active_records if r["headshot"]["face"]),
        "players": active_records,
    }
    active_path = os.path.join(METADATA_DIR, "active.json")
    with open(active_path, "w") as f:
        json.dump(active_index, f, indent=2)
    log(f"Wrote {active_path}")

    log(f"Total players: {len(records)}")
    log(f"With face PNG: {with_headshot}")
    log(f"Missing: {len(records) - with_headshot}")
    log(f"Active players: {len(active_records)}")


if __name__ == "__main__":
    build_index()

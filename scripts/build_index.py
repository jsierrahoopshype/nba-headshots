"""Build the master player and team JSON indexes."""

import json
import os
from datetime import datetime, timezone

from utils import NBA_HEADERS, log, safe_get, slugify

PLAYER_INDEX_URL = "https://stats.nba.com/stats/playerindex?Historical=1&LeagueID=00&Season=2024-25"
FACE_DIR = os.path.join("players", "headshots", "face")
ORIGINAL_DIR = os.path.join("players", "headshots", "original")
METADATA_DIR = os.path.join("players", "metadata")


def fetch_player_list():
    log("Fetching player index from NBA Stats API...")
    resp = safe_get(PLAYER_INDEX_URL, headers=NBA_HEADERS, timeout=30)
    if not resp or resp.status_code != 200:
        log("ERROR: Failed to fetch player index")
        return []

    data = resp.json()
    result_set = data["resultSets"][0]
    headers = result_set["headers"]
    rows = result_set["rowSet"]

    col = {h: i for i, h in enumerate(headers)}
    players = []
    for row in rows:
        players.append({
            "nba_id": row[col["PERSON_ID"]],
            "first_name": row[col["PLAYER_FIRST_NAME"]],
            "last_name": row[col["PLAYER_LAST_NAME"]],
            "full_name": f"{row[col['PLAYER_FIRST_NAME']]} {row[col['PLAYER_LAST_NAME']]}",
            "from_year": row[col["FROM_YEAR"]],
            "to_year": row[col["TO_YEAR"]],
            "roster_status": row[col["ROSTERSTATUS"]],
            "team_id": row[col["TEAM_ID"]],
            "team_abbrev": row[col["TEAM_ABBREVIATION"]],
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
        has_face = os.path.exists(os.path.join(FACE_DIR, f"{nba_id}.png"))
        has_original = os.path.exists(os.path.join(ORIGINAL_DIR, f"{nba_id}.png"))
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
            "slug": slugify(p["full_name"]),
            "team_id": p["team_id"],
            "team_abbrev": p["team_abbrev"],
            "active": p["roster_status"] == 1,
            "seasons_from": p["from_year"],
            "seasons_to": p["to_year"],
            "headshot": {
                "face": has_face,
                "original": has_original,
                "source": source,
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

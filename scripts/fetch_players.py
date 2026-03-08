"""Download NBA player headshots from the NBA CDN."""

import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path("players/headshots")
ORIGINAL_DIR = BASE_DIR / "original"
META_DIR = Path("players/metadata")

ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
META_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}


def ts():
    return datetime.now().strftime("%H:%M:%S")


def get_all_players():
    try:
        req = urllib.request.Request(
            "https://cdn.nba.com/static/json/staticData/playerIndex.json",
            headers=HEADERS,
        )
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())
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
        for r in rows:
            players.append({
                "nba_id": r[ID],
                "first_name": r[FIRST],
                "last_name": r[LAST],
                "full_name": f"{r[FIRST]} {r[LAST]}",
                "team_id": r[TEAM_ID],
                "team_abbrev": r[TEAM_ABB],
                "active": r[STATUS] == 1,
            })
        return players
    except Exception as e:
        print(f"ERROR in get_all_players: {type(e).__name__}: {e}")
        return []


def download_headshot(nba_id):
    out_path = ORIGINAL_DIR / f"{nba_id}.png"
    if out_path.exists():
        return "cached"
    try:
        url = f"https://cdn.nba.com/headshots/nba/latest/1040x760/{nba_id}.png"
        req = urllib.request.Request(url, headers=HEADERS)
        content = urllib.request.urlopen(req, timeout=10).read()
        if len(content) > 5000:
            out_path.write_bytes(content)
            return "success"
        else:
            return "404"
    except Exception as e:
        return f"error: {e}"


if __name__ == "__main__":
    limit = None
    active_only = False
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        elif args[i] == "--active-only":
            active_only = True
            i += 1
        else:
            i += 1

    print(f"[{ts()}] Fetching player index...")
    players = get_all_players()
    if not players:
        print("ERROR: No players returned")
        sys.exit(1)

    print(f"[{ts()}] Got {len(players)} players")

    if active_only:
        players = [p for p in players if p["active"]]

    if limit:
        players = players[:limit]

    print(f"[{ts()}] Downloading headshots for {len(players)} players...")

    success = 0
    cached = 0
    missing = []
    errors = 0
    total = len(players)

    for idx, p in enumerate(players, 1):
        result = download_headshot(p["nba_id"])
        if result == "success":
            success += 1
        elif result == "cached":
            cached += 1
        elif result == "404":
            missing.append({
                "nba_id": p["nba_id"],
                "full_name": p["full_name"],
                "tried_sources": ["nba_cdn"],
            })
        else:
            errors += 1

        if idx % 50 == 0:
            print(f"[{ts()}] {idx}/{total} done - success:{success} cached:{cached} missing:{len(missing)}")

        time.sleep(0.25)

    print(f"[{ts()}] Finished: success:{success} cached:{cached} missing:{len(missing)} errors:{errors}")

    missing_path = META_DIR / "missing.json"
    missing_path.write_text(json.dumps({"players": missing}, indent=2))
    print(f"[{ts()}] Wrote {missing_path} ({len(missing)} entries)")
    print("Done.")

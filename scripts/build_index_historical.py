"""Build index files covering the historical players, without touching players.json.

Writes two new files:

    players/metadata/players_historical.json   only the newly added players
    players/metadata/players_all.json          existing + historical, merged

Deliberately does NOT write `players.json`, `active.json` or `missing.json`.
Everything already consuming those keeps working byte-for-byte. When you want a
consumer to see the full set, point it at `players_all.json`; until then nothing
changes for anyone.

Record shape is identical to `build_index.py` output, so the same SDK accessors
work: nba_id, full_name, first_name, last_name, slug, team_id, team_abbrev,
active, seasons_from, seasons_to, headshot{face, original, source, filename}.

Usage (from the repo root):

    python scripts/build_index_historical.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import log, slugify

FACE_DIR = Path("players/headshots/face")
ORIGINAL_DIR = Path("players/headshots/original")
META_DIR = Path("players/metadata")

EXISTING_INDEX = META_DIR / "players.json"
ROSTER = META_DIR / "historical_roster.json"
CROSSWALK = META_DIR / "espn_crosswalk.json"

OUT_HISTORICAL = META_DIR / "players_historical.json"
OUT_ALL = META_DIR / "players_all.json"


def load_json(path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log(f"Could not read {path}: {e}")
        return default


def build_record(p, crosswalk):
    nba_id = p["nba_id"]
    slug = p.get("slug") or slugify(p["full_name"])
    filename = f"{nba_id}-{slug}.png"

    has_face = (FACE_DIR / filename).exists()
    has_original = (ORIGINAL_DIR / filename).exists()
    espn_id = crosswalk.get(str(nba_id))

    record = {
        "nba_id": nba_id,
        "full_name": p["full_name"],
        "first_name": p.get("first_name", ""),
        "last_name": p.get("last_name", ""),
        "slug": slug,
        "team_id": p.get("team_id"),
        "team_abbrev": p.get("team_abbrev", ""),
        "active": p.get("roster_status") == 1,
        "seasons_from": p.get("from_year"),
        "seasons_to": p.get("to_year"),
        "headshot": {
            "face": has_face,
            "original": has_original,
            "source": "espn" if espn_id else "nba_cdn",
            "filename": filename,
        },
    }
    if espn_id:
        record["espn_id"] = int(espn_id)
    return record


def main():
    roster = load_json(ROSTER)
    if not roster:
        log(f"{ROSTER} not found. Run scripts/fetch_historical.py first.")
        return 1

    crosswalk = load_json(CROSSWALK, {}) or {}
    if crosswalk:
        log(f"Loaded ESPN crosswalk ({len(crosswalk)} entries)")

    now = datetime.now(timezone.utc).isoformat()

    records = [build_record(p, crosswalk) for p in roster.get("players", [])]
    # Only keep players that actually ended up with an image. The rest stay
    # listed in historical_missing.json rather than padding the index.
    records = [r for r in records if r["headshot"]["face"] or r["headshot"]["original"]]

    hist = {
        "generated_at": now,
        "total_players": len(records),
        "with_headshot": sum(1 for r in records if r["headshot"]["face"]),
        "players": records,
    }
    OUT_HISTORICAL.write_text(json.dumps(hist, indent=2), encoding="utf-8")
    log(f"Wrote {OUT_HISTORICAL} ({len(records)} players)")

    existing = load_json(EXISTING_INDEX, {"players": []}) or {"players": []}
    existing_players = existing.get("players", [])

    # Existing records win on collision. This file is a superset, never a
    # rewrite of anything already published.
    seen = {str(r["nba_id"]) for r in existing_players}
    merged = list(existing_players) + [r for r in records
                                       if str(r["nba_id"]) not in seen]
    merged.sort(key=lambda r: (r.get("last_name") or "", r.get("first_name") or ""))

    allidx = {
        "generated_at": now,
        "total_players": len(merged),
        "with_headshot": sum(1 for r in merged if r["headshot"]["face"]),
        "players": merged,
    }
    OUT_ALL.write_text(json.dumps(allidx, indent=2), encoding="utf-8")
    log(f"Wrote {OUT_ALL} ({len(merged)} players, "
        f"{allidx['with_headshot']} with a face crop)")

    log("")
    log("players.json, active.json and missing.json were not modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

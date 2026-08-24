"""Download headshots for players missing from the current-season index.

Why this exists
---------------
`fetch_players.py` and `build_index.py` both source from
`cdn.nba.com/static/json/staticData/playerIndex.json`, which only lists players
on a current roster. That caps the repo at the modern era: 572 players, earliest
debut 2003. Every retired player is absent, so any historical list renders
silhouettes.

This script works from an all-time roster of 5,103 players and downloads only
the ones not already present, which is 4,550.

The roster comes from `players/metadata/historical_roster.json`, which ships
alongside this script already built. That file was generated from the nba_api
project's static player index, so the roster step needs no call to
`stats.nba.com` at all: no browser headers to keep working, no season string to
guess, and no exposure to the datacenter IP block on that host. If the file is
absent the script falls back to `commonallplayers`, but you should not need it.

It is strictly additive
-----------------------
  * Nothing existing is read for anything except a skip list.
  * A file is never overwritten. If `{id}-{slug}.png` already exists in
    original/ or face/, that player is skipped outright.
  * `players.json`, `active.json` and `missing.json` are not touched. Run
    `build_index_historical.py` afterwards to write the new index files.
  * Naming uses `utils.slugify`, the repo's own function, so the convention
    matches exactly, including its handling of non-ASCII characters.

Placeholder detection
---------------------
For many retired players the NBA CDN does not 404. It returns a generic
silhouette image, byte-identical across every id that lacks a real photo. The
existing `len(content) > 5000` guard passes those straight through, which would
quietly fill the repo with thousands of identical grey outlines. This script
hashes every download, auto-detects any hash shared by several ids, and moves
those files to `players/headshots/_rejected/` rather than leaving them in place.

Usage (Windows, from the repo root)
-----------------------------------
    python scripts/fetch_historical.py --dry-run
    python scripts/fetch_historical.py --limit 50
    python scripts/fetch_historical.py
    python scripts/process_faces.py --new-only
    python scripts/build_index_historical.py

Safe to interrupt and re-run: already-downloaded players are skipped.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import NBA_HEADERS, STATIC_CDN_HEADERS, log, safe_get, slugify

ORIGINAL_DIR = Path("players/headshots/original")
FACE_DIR = Path("players/headshots/face")
REJECT_DIR = Path("players/headshots/_rejected")
META_DIR = Path("players/metadata")

EXISTING_INDEX = META_DIR / "players.json"
OUT_ROSTER = META_DIR / "historical_roster.json"
OUT_MISSING = META_DIR / "historical_missing.json"

CDN_HEADSHOT = "https://cdn.nba.com/headshots/nba/latest/1040x760/{id}.png"

MIN_BYTES = 5000          # same threshold the existing fetch script uses
PLACEHOLDER_MIN_HITS = 3  # a hash seen this many times is a generic placeholder
SLEEP = 0.25              # be polite; the existing script uses the same


def current_season():
    """NBA season string for the stats API, e.g. '2025-26'."""
    now = datetime.now()
    start = now.year if now.month >= 10 else now.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def load_prebuilt_roster(path):
    """The shipped all-time roster. No network, no NBA host involved."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log(f"Could not read {p}: {e}")
        return None

    players = data.get("players", [])
    if not players:
        return None
    log(f"Using prebuilt roster: {p} ({len(players)} players, "
        f"source: {data.get('source', 'unknown')})")
    return players


def fetch_all_time_roster():
    """Fallback only: all players in NBA history, from commonallplayers."""
    for season in (current_season(), f"{datetime.now().year - 1}-"
                   f"{str(datetime.now().year)[2:]}"):
        url = ("https://stats.nba.com/stats/commonallplayers"
               f"?LeagueID=00&Season={season}&IsOnlyCurrentSeason=0")
        log(f"Requesting all-time roster for {season}...")
        resp = safe_get(url, headers=NBA_HEADERS, timeout=30, retries=3)
        if resp is None or resp.status_code != 200:
            log(f"  no usable response for {season}")
            continue

        try:
            data = resp.json()
            rs = data["resultSets"][0]
            head, rows = rs["headers"], rs["rowSet"]
        except (ValueError, KeyError, IndexError) as e:
            log(f"  unexpected payload: {type(e).__name__}: {e}")
            continue

        ID = head.index("PERSON_ID")
        DISPLAY = head.index("DISPLAY_FIRST_LAST")
        COMMA = head.index("DISPLAY_LAST_COMMA_FIRST")
        FROM = head.index("FROM_YEAR")
        TO = head.index("TO_YEAR")
        TEAM_ID = head.index("TEAM_ID")
        TEAM_ABB = head.index("TEAM_ABBREVIATION")
        STATUS = head.index("ROSTERSTATUS")

        players = []
        for r in rows:
            full = (r[DISPLAY] or "").strip()
            if not full:
                continue
            # 'Abdul-Jabbar, Kareem' splits far more reliably than a space split
            # on names like 'Nene' or 'Metta World Peace'.
            comma = (r[COMMA] or "").strip()
            if "," in comma:
                last, first = [s.strip() for s in comma.split(",", 1)]
            else:
                parts = full.split(" ", 1)
                first, last = parts[0], (parts[1] if len(parts) > 1 else "")

            players.append({
                "nba_id": r[ID],
                "full_name": full,
                "first_name": first,
                "last_name": last,
                "slug": slugify(full),
                "from_year": r[FROM],
                "to_year": r[TO],
                "team_id": r[TEAM_ID],
                "team_abbrev": (r[TEAM_ABB] or "").strip(),
                "roster_status": r[STATUS],
            })

        log(f"  got {len(players)} players")
        return players

    log("ERROR: could not reach stats.nba.com.")
    log("Note: the NBA blocks most datacenter IPs. Run this from your own "
        "machine, not from a Space or a cloud box.")
    return []


def already_have_ids():
    """Every nba_id already covered, from the index and from files on disk."""
    have = set()

    if EXISTING_INDEX.exists():
        try:
            data = json.loads(EXISTING_INDEX.read_text(encoding="utf-8"))
            for p in data.get("players", []):
                have.add(str(p.get("nba_id")))
        except (OSError, ValueError) as e:
            log(f"Could not read {EXISTING_INDEX}: {e}")

    # Files win over the index: never re-download something already on disk.
    for d in (ORIGINAL_DIR, FACE_DIR):
        if d.exists():
            for f in os.listdir(d):
                if f.endswith(".png") and "-" in f:
                    have.add(f.split("-", 1)[0])

    return have


def download(nba_id, slug):
    """Returns (status, sha1). Status is saved | exists | missing | error."""
    out = ORIGINAL_DIR / f"{nba_id}-{slug}.png"
    if out.exists():
        return "exists", None

    resp = safe_get(CDN_HEADSHOT.format(id=nba_id),
                    headers=STATIC_CDN_HEADERS, timeout=15, retries=2)
    if resp is None:
        return "error", None
    if resp.status_code != 200:
        return "missing", None

    content = resp.content
    if len(content) < MIN_BYTES:
        return "missing", None

    digest = hashlib.sha1(content).hexdigest()
    out.write_bytes(content)
    return "saved", digest


def quarantine_placeholders(by_hash):
    """
    Move away any image the CDN served for several different players.

    Returns the filenames moved. The caller needs them because the CDN answers
    HTTP 200 for a placeholder, so these players look like successful downloads
    right up until this point. If they are not folded back into the missing
    list, the run reports zero misses while having found nothing for them.
    """
    REJECT_DIR.mkdir(parents=True, exist_ok=True)
    moved = []
    for digest, names in by_hash.items():
        if len(names) < PLACEHOLDER_MIN_HITS:
            continue
        log(f"Placeholder detected ({digest[:10]}), served for {len(names)} "
            f"players. Moving to {REJECT_DIR}/")
        for fname in names:
            src = ORIGINAL_DIR / fname
            if src.exists():
                shutil.move(str(src), str(REJECT_DIR / fname))
                moved.append(fname)
    return moved


def main():
    ap = argparse.ArgumentParser(
        description="Add headshots for players missing from the current index.")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after this many downloads, for a test run")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be fetched, download nothing")
    ap.add_argument("--min-year", type=int, default=0,
                    help="only players whose last season is this year or later; "
                         "needs season years, which the prebuilt roster does "
                         "not carry, so this only applies to the fallback path")
    ap.add_argument("--roster", default=str(OUT_ROSTER),
                    help="prebuilt roster JSON; falls back to stats.nba.com "
                         "if the file is missing")
    ap.add_argument("--sleep", type=float, default=SLEEP,
                    help=f"delay between downloads, default {SLEEP}")
    args = ap.parse_args()

    ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    roster = load_prebuilt_roster(args.roster)
    if roster is None:
        log("No prebuilt roster found, falling back to stats.nba.com")
        roster = fetch_all_time_roster()
        if roster:
            # build_index_historical.py reads this file, so persist whatever the
            # fallback produced in the same shape as the shipped roster.
            OUT_ROSTER.write_text(json.dumps(
                {"generated_at": datetime.now().isoformat(),
                 "source": "stats.nba.com commonallplayers",
                 "total": len(roster), "players": roster}, indent=2),
                encoding="utf-8")
            log(f"Wrote {OUT_ROSTER}")
    if not roster:
        return 1

    have = already_have_ids()
    todo = [p for p in roster if str(p["nba_id"]) not in have]

    if args.min_year:
        todo = [p for p in todo
                if str(p.get("to_year") or "0").isdigit()
                and int(p["to_year"]) >= args.min_year]

    log(f"Roster:          {len(roster)}")
    log(f"Already covered: {len(roster) - len(todo)}")
    log(f"To fetch:        {len(todo)}")
    est = len(todo) * (args.sleep + 0.35) / 60.0
    log(f"Rough estimate:  {est:.0f} minutes")

    if args.dry_run:
        for p in todo[:25]:
            years = ""
            if p.get("from_year") and p.get("to_year"):
                years = f" ({p['from_year']}-{p['to_year']})"
            log(f"  would fetch {p['nba_id']}-{p['slug']}{years}")
        if len(todo) > 25:
            log(f"  ... and {len(todo) - 25} more")
        return 0

    if args.limit:
        todo = todo[:args.limit]

    saved = skipped = missing = errors = 0
    by_hash = defaultdict(list)
    no_image = []
    by_filename = {}

    for i, p in enumerate(todo, 1):
        status, digest = download(p["nba_id"], p["slug"])
        if status == "saved":
            saved += 1
            fname = f"{p['nba_id']}-{p['slug']}.png"
            by_hash[digest].append(fname)
            by_filename[fname] = p
        elif status == "exists":
            skipped += 1
        elif status == "missing":
            missing += 1
            no_image.append({"nba_id": p["nba_id"], "full_name": p["full_name"],
                             "tried_sources": ["nba_cdn"]})
        else:
            errors += 1

        if i % 50 == 0:
            log(f"{i}/{len(todo)} saved:{saved} missing:{missing} errors:{errors}")
        time.sleep(args.sleep)

    moved = quarantine_placeholders(by_hash)

    # A quarantined player has no usable image, so it belongs in the missing
    # list next to the genuine 404s. Without this the report claims success.
    for fname in moved:
        p = by_filename.get(fname)
        if p:
            no_image.append({"nba_id": p["nba_id"], "full_name": p["full_name"],
                             "tried_sources": ["nba_cdn"], "reason": "placeholder"})
    saved -= len(moved)

    OUT_MISSING.write_text(json.dumps(
        {"generated_at": datetime.now().isoformat(),
         "count": len(no_image), "players": no_image}, indent=2), encoding="utf-8")

    real = saved
    total = real + len(no_image)
    pct = (100.0 * real / total) if total else 0.0

    log("")
    log(f"Real images:  {real}")
    log(f"Skipped:      {skipped}")
    log(f"No image:     {len(no_image)}  ({missing} 404, {len(moved)} placeholder)")
    log(f"Errors:       {errors}")
    log(f"Hit rate:     {pct:.0f}%")
    log(f"Wrote {OUT_MISSING}")
    log("")
    log("Next: python scripts/process_faces.py --new-only")
    log("Then: python scripts/build_index_historical.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

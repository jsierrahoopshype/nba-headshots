"""Cross-reference missing NBA players with ESPN to fill headshot gaps."""

import json
import os
import time

from utils import log, safe_get

ESPN_ATHLETES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/athletes?limit=1000&page={page}"
ESPN_HEADSHOT_URL = "https://a.espncdn.com/combiner/i?img=/i/headshots/nba/players/full/{espn_id}.png&w=1040&h=760"
ORIGINAL_DIR = os.path.join("players", "headshots", "original")
METADATA_DIR = os.path.join("players", "metadata")


def load_missing():
    path = os.path.join(METADATA_DIR, "missing.json")
    if not os.path.exists(path):
        log("missing.json not found — run fetch_players.py first")
        return []
    with open(path) as f:
        return json.load(f)


def fetch_espn_athletes():
    """Paginate ESPN API and return list of {id, full_name, first, last}."""
    all_athletes = []
    page = 1
    while True:
        log(f"Fetching ESPN athletes page {page}...")
        resp = safe_get(ESPN_ATHLETES_URL.format(page=page), timeout=20)
        if not resp or resp.status_code != 200:
            break

        data = resp.json()
        items = data.get("items", [])
        if not items:
            athletes = data.get("athletes", [])
            if not athletes:
                break
            for a in athletes:
                all_athletes.append({
                    "espn_id": a["id"],
                    "full_name": a.get("fullName", a.get("displayName", "")),
                    "first_name": a.get("firstName", ""),
                    "last_name": a.get("lastName", ""),
                })
            if len(athletes) < 1000:
                break
        else:
            for item in items:
                resp2 = safe_get(item.get("$ref", item.get("href", "")), timeout=15)
                if resp2 and resp2.status_code == 200:
                    a = resp2.json()
                    all_athletes.append({
                        "espn_id": a["id"],
                        "full_name": a.get("fullName", a.get("displayName", "")),
                        "first_name": a.get("firstName", ""),
                        "last_name": a.get("lastName", ""),
                    })
                    time.sleep(0.1)
            if len(items) < 1000:
                break

        page += 1
        time.sleep(0.5)

    log(f"Total ESPN athletes fetched: {len(all_athletes)}")
    return all_athletes


def match_players(missing, espn_athletes):
    """Match missing players to ESPN athletes by name."""
    # Build lookup structures
    by_full_name = {}
    by_last_first_initial = {}
    for a in espn_athletes:
        name = a["full_name"].strip().lower()
        by_full_name[name] = a
        last = a["last_name"].strip().lower()
        first_initial = a["first_name"].strip().lower()[:1] if a["first_name"] else ""
        key = f"{last}_{first_initial}"
        if key not in by_last_first_initial:
            by_last_first_initial[key] = a

    matches = {}
    for mp in missing:
        full = mp["full_name"].strip().lower()
        if full in by_full_name:
            matches[mp["nba_id"]] = by_full_name[full]
            continue
        parts = mp["full_name"].strip().split()
        if len(parts) >= 2:
            last = parts[-1].lower()
            first_initial = parts[0][0].lower()
            key = f"{last}_{first_initial}"
            if key in by_last_first_initial:
                matches[mp["nba_id"]] = by_last_first_initial[key]

    log(f"Matched {len(matches)} missing players to ESPN")
    return matches


def download_espn_headshots(missing, matches):
    """Download headshots from ESPN for matched players."""
    os.makedirs(ORIGINAL_DIR, exist_ok=True)
    crosswalk = {}
    filled = 0

    for mp in missing:
        nba_id = mp["nba_id"]
        if nba_id not in matches:
            continue

        espn_data = matches[nba_id]
        espn_id = espn_data["espn_id"]
        crosswalk[str(nba_id)] = str(espn_id)

        out_path = os.path.join(ORIGINAL_DIR, f"{nba_id}.png")
        if os.path.exists(out_path):
            filled += 1
            continue

        url = ESPN_HEADSHOT_URL.format(espn_id=espn_id)
        resp = safe_get(url, timeout=15)
        if resp and resp.status_code == 200 and len(resp.content) > 5000:
            with open(out_path, "wb") as f:
                f.write(resp.content)
            filled += 1
            log(f"ESPN fill: {mp['full_name']} (NBA {nba_id} → ESPN {espn_id})")

        # Mark espn as tried
        if "espn" not in mp.get("tried_sources", []):
            mp.setdefault("tried_sources", []).append("espn")

        time.sleep(0.25)

    log(f"Filled {filled} headshots from ESPN")

    # Save crosswalk
    crosswalk_path = os.path.join(METADATA_DIR, "espn_crosswalk.json")
    with open(crosswalk_path, "w") as f:
        json.dump(crosswalk, f, indent=2)
    log(f"Wrote {crosswalk_path}")

    # Update missing.json
    missing_path = os.path.join(METADATA_DIR, "missing.json")
    with open(missing_path, "w") as f:
        json.dump(missing, f, indent=2)
    log(f"Updated {missing_path}")


if __name__ == "__main__":
    missing = load_missing()
    if not missing:
        log("No missing players to process")
    else:
        espn_athletes = fetch_espn_athletes()
        if espn_athletes:
            matches = match_players(missing, espn_athletes)
            download_espn_headshots(missing, matches)

#!/usr/bin/env python3
"""
Backfill headshots for players that exist in the NBA CDN but not in players_all.json.

Input: scripts/missing_allstars.txt  (one per line: "Name|firstSeasonStartYear|lastSeasonEndYear",
        lines starting with # ignored). Names are the game-data names (ASCII, "Tiny Archibald").
Steps per player:
  1. resolve the NBA id from stats.nba.com playerindex (Historical=1), matching by normalized name
     and career years (disambiguates the two Larry Johnsons, Eddie Johnsons, etc.);
  2. download cdn.nba.com/headshots/nba/latest/1040x760/<id>.png into players/headshots/original/;
  3. write the uniform crop into players/headshots/face2/ (same face-lock as recrop_faces.py),
     a 256px copy into players/headshots/face/, a 64px thumb into players/headshots/thumb/,
     and the 160px WebP into players/headshots/face2-160/;
  4. append the player to players/metadata/players_all.json and players_historical.json.
Additive only: existing files and records are never touched; re-runs skip what exists.

Run from the repo root:   python scripts\\backfill_missing.py
Needs: requests, pillow, opencv-python<5 (the same as recrop_faces.py). stats.nba.com must be
reachable from this machine (it blocks cloud IPs, which is why this runs on the desktop).
"""
import json, os, re, sys, time, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import NBA_HEADERS, STATIC_CDN_HEADERS, slugify, log   # noqa: E402
import requests                                                    # noqa: E402
from PIL import Image                                              # noqa: E402
import recrop_faces as rc                                          # noqa: E402  (face-lock crop helpers)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HS = os.path.join(ROOT, "players", "headshots")
DIRS = {k: os.path.join(HS, k) for k in ("original", "face", "face2", "face2-160", "thumb")}
for d in DIRS.values():
    os.makedirs(d, exist_ok=True)
META = os.path.join(ROOT, "players", "metadata")
ALL = os.path.join(META, "players_all.json")
HIST = os.path.join(META, "players_historical.json")
LIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "missing_allstars.txt")

# game-data names that differ from the NBA's registered names
ALIASES = {
    "tiny archibald": "nate archibald", "fast eddie johnson": "eddie johnson", "hot rod hundley": "rod hundley",
    "jo jo white": "jojo white", "world b free": "world free", "micheal ray richardson": "michael ray richardson",
    "predrag stojakovic": "peja stojakovic", "maurice williams": "mo williams", "larry johnson": "larry johnson",
    "tommy heinsohn": "tom heinsohn", "bj armstrong": "b.j. armstrong", "red kerr": "johnny kerr",
    "clifford robinson": "cliff robinson", "jack twyman": "jack twyman", "nat clifton": "nat clifton",
}


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = s.replace("'", "").replace(".", "").replace("-", " ")
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return " ".join(s.split())


def player_index():
    url = "https://stats.nba.com/stats/playerindex?Historical=1&LeagueID=00&Season=2025-26"
    log("fetching playerindex (Historical=1)")
    r = requests.get(url, headers=NBA_HEADERS, timeout=40)
    r.raise_for_status()
    rs = r.json()["resultSets"][0]
    H = rs["headers"]
    ix = {h: H.index(h) for h in ("PERSON_ID", "PLAYER_FIRST_NAME", "PLAYER_LAST_NAME", "FROM_YEAR", "TO_YEAR", "TEAM_ID", "TEAM_ABBREVIATION", "ROSTER_STATUS")}
    out = []
    for row in rs["rowSet"]:
        out.append({
            "nba_id": row[ix["PERSON_ID"]], "first_name": row[ix["PLAYER_FIRST_NAME"]] or "", "last_name": row[ix["PLAYER_LAST_NAME"]] or "",
            "from_year": int(row[ix["FROM_YEAR"]] or 0), "to_year": int(row[ix["TO_YEAR"]] or 0),
            "team_id": row[ix["TEAM_ID"]], "team_abbrev": row[ix["TEAM_ABBREVIATION"]] or "", "roster_status": row[ix["ROSTER_STATUS"]],
        })
    log(f"{len(out)} players in index")
    return out


def resolve(name, y0, y1, index):
    key = ALIASES.get(norm(name), norm(name))
    cands = [p for p in index if norm(p["first_name"] + " " + p["last_name"]) == key]
    if not cands:   # last name + first initial, then career overlap decides
        ln = key.split()[-1]
        cands = [p for p in index if norm(p["last_name"]) == ln and norm(p["first_name"])[:1] == key[:1]]
    if not cands:
        return None
    # FROM_YEAR is the season start year, same convention as the game data's y[0]
    cands.sort(key=lambda p: abs(p["from_year"] - y0) + abs(p["to_year"] - y1))
    best = cands[0]
    if abs(best["from_year"] - y0) > 2:
        return None
    return best


def main():
    if not os.path.exists(LIST):
        sys.exit(f"missing {LIST}")
    allidx = json.load(open(ALL, encoding="utf-8"))
    hist = json.load(open(HIST, encoding="utf-8")) if os.path.exists(HIST) else {"players": []}
    have = {p["nba_id"] for p in allidx["players"]}
    index = player_index()
    todo = []
    for line in open(LIST, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, y0, y1 = line.split("|")
        todo.append((name, int(y0), int(y1)))
    added, unresolved, missing_cdn, skipped = [], [], [], 0
    for name, y0, y1 in todo:
        p = resolve(name, y0, y1, index)
        if not p:
            unresolved.append(name); continue
        if p["nba_id"] in have:
            skipped += 1; continue
        full = f'{p["first_name"]} {p["last_name"]}'.strip()
        slug = slugify(full)
        fn = f'{p["nba_id"]}-{slug}.png'
        orig = os.path.join(DIRS["original"], fn)
        if not os.path.exists(orig):
            url = f'https://cdn.nba.com/headshots/nba/latest/1040x760/{p["nba_id"]}.png'
            r = requests.get(url, headers=STATIC_CDN_HEADERS, timeout=20)
            if r.status_code != 200 or len(r.content) < 2000:
                missing_cdn.append(f"{name} ({p['nba_id']})"); continue
            open(orig, "wb").write(r.content)
            time.sleep(0.25)
        # uniform face2 crop with the repo's own face-lock, then the small copies
        img = rc.load_bgr(orig)
        face = rc.best_face(img)
        crop = rc.crop_on_face(img, face) if face is not None else rc.center_crop(img)
        f2 = os.path.join(DIRS["face2"], fn)
        if not os.path.exists(f2):
            rc.cv2.imwrite(f2, crop)
        pil = Image.open(f2).convert("RGB")
        fp = os.path.join(DIRS["face"], fn)
        if not os.path.exists(fp):
            pil.resize((256, 256), Image.LANCZOS).save(fp, "PNG", optimize=True)
        tp = os.path.join(DIRS["thumb"], fn)
        if not os.path.exists(tp):
            pil.resize((64, 64), Image.LANCZOS).save(tp, "PNG", optimize=True)
        wp = os.path.join(DIRS["face2-160"], fn[:-4] + ".webp")
        if not os.path.exists(wp):
            pil.resize((160, 160), Image.LANCZOS).save(wp, "WEBP", quality=82, method=6)
        rec = {
            "nba_id": p["nba_id"], "full_name": full, "first_name": p["first_name"], "last_name": p["last_name"], "slug": slug,
            "team_id": p["team_id"], "team_abbrev": p["team_abbrev"], "active": p["roster_status"] == 1,
            "seasons_from": p["from_year"], "seasons_to": p["to_year"],
            "headshot": {"face": True, "original": True, "source": "nba_cdn", "filename": fn},
        }
        allidx["players"].append(rec); hist.setdefault("players", []).append(rec); have.add(p["nba_id"])
        added.append(f"{name} -> {fn}" + ("" if face is not None else "  [center crop, no face found]"))
        print("OK  ", added[-1])
    allidx["total_players"] = len(allidx["players"]); allidx["with_headshot"] = sum(1 for p in allidx["players"] if p["headshot"].get("face"))
    json.dump(allidx, open(ALL, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    json.dump(hist, open(HIST, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    log(f"added {len(added)}, already indexed {skipped}, no CDN image {len(missing_cdn)}, unresolved names {len(unresolved)}")
    if missing_cdn:
        print("\nNo CDN headshot (nothing to do):\n  " + "\n  ".join(missing_cdn))
    if unresolved:
        print("\nCould not match in playerindex (add an alias to ALIASES):\n  " + "\n  ".join(unresolved))


if __name__ == "__main__":
    main()

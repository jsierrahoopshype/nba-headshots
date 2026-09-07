#!/usr/bin/env python3
"""
One-shot backfill for legends whose cdn.nba.com headshot is a placeholder,
using ESPN's headshot CDN instead. Currently: Jason Kidd and Alex English.

Save this file as   scripts\\backfill_espn_legends.py   in the nba-headshots
repo, then run from the repo root on the desktop:

    python scripts\backfill_espn_legends.py

Additive only, same pattern as backfill_missing.py: writes original/, the
face-lock face2/ crop, face/, thumb/ and face2-160/ .webp, and appends the
players to players_all.json and players_historical.json. Re-runs skip files
that already exist. Needs the same deps as backfill_missing.py.
After it reports OK for both, commit and push the repo as usual.
"""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from utils import STATIC_CDN_HEADERS, slugify, log   # noqa: E402
import requests                                       # noqa: E402
from PIL import Image                                 # noqa: E402
import recrop_faces as rc                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HS = os.path.join(ROOT, "players", "headshots")
DIRS = {k: os.path.join(HS, k) for k in ("original", "face", "face2", "face2-160", "thumb")}
for d in DIRS.values():
    os.makedirs(d, exist_ok=True)
META = os.path.join(ROOT, "players", "metadata")
ALL = os.path.join(META, "players_all.json")
HIST = os.path.join(META, "players_historical.json")

ESPN_URL = "https://a.espncdn.com/combiner/i?img=/i/headshots/nba/players/full/{espn_id}.png&w=1040&h=760"

# (full name, NBA id, ESPN id, first name, last name, from_year, to_year, last team abbrev)
LEGENDS = [
    ("Jason Kidd",  467,   429,  "Jason", "Kidd",    1994, 2012, "NYK"),
    ("Alex English", 76673, 4900, "Alex",  "English", 1976, 1990, "DAL"),
]


def looks_like_placeholder(path):
    """ESPN serves a generic gray silhouette for players with no photo -
    tiny file and almost no color variance."""
    if os.path.getsize(path) < 8000:
        return True
    im = Image.open(path).convert("L").resize((64, 64))
    px = list(im.getdata())
    mean = sum(px) / len(px)
    var = sum((p - mean) ** 2 for p in px) / len(px)
    return var < 200


def main():
    allidx = json.load(open(ALL, encoding="utf-8"))
    hist = json.load(open(HIST, encoding="utf-8")) if os.path.exists(HIST) else {"players": []}
    have = {p["nba_id"] for p in allidx["players"]}
    added, failed = [], []

    for full, nba_id, espn_id, first, last, y0, y1, abbrev in LEGENDS:
        if nba_id in have:
            log(f"{full}: already indexed, skipping")
            continue
        slug = slugify(full)
        fn = f"{nba_id}-{slug}.png"
        orig = os.path.join(DIRS["original"], fn)
        if not os.path.exists(orig):
            url = ESPN_URL.format(espn_id=espn_id)
            log(f"{full}: fetching {url}")
            r = requests.get(url, headers=STATIC_CDN_HEADERS, timeout=20)
            if r.status_code != 200 or len(r.content) < 2000:
                failed.append(f"{full}: ESPN returned {r.status_code} / {len(r.content)} bytes")
                continue
            open(orig, "wb").write(r.content)
            time.sleep(0.25)
        if looks_like_placeholder(orig):
            os.remove(orig)
            failed.append(f"{full}: ESPN image is a placeholder silhouette - no real photo there")
            continue

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
            "nba_id": nba_id, "full_name": full, "first_name": first, "last_name": last, "slug": slug,
            "team_id": 0, "team_abbrev": abbrev, "active": False,
            "seasons_from": y0, "seasons_to": y1,
            "headshot": {"face": True, "original": True, "source": "espn_cdn", "filename": fn},
        }
        allidx["players"].append(rec)
        hist.setdefault("players", []).append(rec)
        have.add(nba_id)
        added.append(f"{full} -> {fn}" + ("" if face is not None else "  [center crop, no face found]"))
        print("OK  ", added[-1])

    allidx["total_players"] = len(allidx["players"])
    allidx["with_headshot"] = sum(1 for p in allidx["players"] if p["headshot"].get("face"))
    json.dump(allidx, open(ALL, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    json.dump(hist, open(HIST, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    log(f"added {len(added)}, failed {len(failed)}")
    if failed:
        print("\nNothing usable on ESPN for:\n  " + "\n  ".join(failed) +
              "\n(For those, drop any square-ish photo you like into players/headshots/original/ " +
              "under the same filename and re-run - the script will crop it.)")


if __name__ == "__main__":
    main()

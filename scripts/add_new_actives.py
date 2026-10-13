"""Add players who joined the league since the last full pipeline run (rookies, new signings).

Additive only. For every ACTIVE player in the NBA's player index who has no
players/headshots/face/ file yet, this:
  1. downloads the NBA CDN headshot (skips players whose photo is still the blank silhouette),
  2. writes face/ (256px, transparent background) and thumb/ (64px) the way the original
     pipeline did: background removed, head-and-shoulders crop, padded to a square,
  3. writes face2/ (520px) with recrop_faces.py's own functions, so the framing matches
     every other face2 crop,
  4. writes face2-160/ (160px WebP) like make_face2_160.py,
  5. appends the player to players.json, active.json and players_all.json.
Existing files and existing metadata rows are never touched. face-tight/ is built afterwards
by scripts/build_face_tight.py (the workflow runs it).

Run from the repo root:  python scripts/add_new_actives.py [--dry-run] [--limit N]
Needs: pillow numpy opencv-python-headless<5 curl_cffi rembg (rembg optional: falls back to a colour key).
"""

import argparse
import io
import json
import os
import re
import sys
import urllib.request

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.chdir(ROOT)

HS = os.path.join("players", "headshots")
META = os.path.join("players", "metadata")
INDEX_URL = "https://cdn.nba.com/static/json/staticData/playerIndex.json"
PHOTO_URL = "https://cdn.nba.com/headshots/nba/latest/1040x760/{}.png"
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nba.com/"}


def slugify(name):
    """Same rule as fetch_players.py, so filenames match the rest of the repo."""
    name = name.lower().replace("'", "").replace(".", "")
    name = re.sub(r"\s+", "-", name.strip())
    return re.sub(r"[^a-z0-9-]", "", name)


def get(url, timeout=30):
    """cdn.nba.com turns away plain scripts from cloud machines, so look like Chrome when curl_cffi is there."""
    try:
        from curl_cffi import requests as creq
    except ImportError:
        return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
    r = creq.get(url, impersonate="chrome", timeout=timeout, headers={"Referer": "https://www.nba.com/"})
    r.raise_for_status()
    return r.content


def active_players():
    data = json.loads(get(INDEX_URL))
    rs = data["resultSets"][0]
    h = rs["headers"]
    ix = {k: h.index(k) for k in ("PERSON_ID", "PLAYER_FIRST_NAME", "PLAYER_LAST_NAME", "TEAM_ID",
                                  "TEAM_ABBREVIATION", "ROSTER_STATUS", "FROM_YEAR", "TO_YEAR") if k in h}
    out = []
    for r in rs["rowSet"]:
        if not r[ix["ROSTER_STATUS"]]:
            continue
        first, last = r[ix["PLAYER_FIRST_NAME"]] or "", r[ix["PLAYER_LAST_NAME"]] or ""
        full = f"{first} {last}".strip()
        out.append({
            "nba_id": r[ix["PERSON_ID"]], "full_name": full, "first_name": first, "last_name": last,
            "slug": slugify(full), "team_id": r[ix["TEAM_ID"]], "team_abbrev": r[ix["TEAM_ABBREVIATION"]],
            "active": True,
            "seasons_from": str(r[ix["FROM_YEAR"]]) if "FROM_YEAR" in ix else "",
            "seasons_to": str(r[ix["TO_YEAR"]]) if "TO_YEAR" in ix else "",
        })
    return out


try:
    from rembg import remove as rembg_remove
except ImportError:
    rembg_remove = None


def remove_bg(img):
    # NBA CDN headshots already come with a transparent background; the slow AI model is only
    # needed when one doesn't (a full class of rookies through it took over 30 minutes).
    alpha = np.array(img.convert("RGBA"))[:, :, 3]
    if (alpha == 0).mean() > 0.05:
        return img
    if rembg_remove:
        return rembg_remove(img)
    rgba = np.array(img.convert("RGBA"))
    r, g, b = (rgba[:, :, i].astype(int) for i in range(3))
    mask = (abs(r - g) < 35) & (abs(g - b) < 35) & (r > 160)   # NBA grey backdrop
    rgba[mask, 3] = 0
    return Image.fromarray(rgba)


def face_and_thumb(original):
    """process_faces.py's recipe: remove background, crop 15-85% wide / 2-70% tall, pad square."""
    img = remove_bg(original.convert("RGBA")).convert("RGBA")
    w, h = img.size
    crop = img.crop((int(w * 0.15), int(h * 0.02), int(w * 0.85), int(h * 0.70)))
    cw, ch = crop.size
    side = max(cw, ch)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(crop, ((side - cw) // 2, (side - ch) // 2), crop)
    return square.resize((256, 256), Image.LANCZOS), square.resize((64, 64), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    import cv2
    import recrop_faces as rc   # its own face2 functions (cascade, crop_on_face, center_crop)

    have = {f.split("-", 1)[0] for f in os.listdir(os.path.join(HS, "face")) if f.endswith(".png")}
    todo = [p for p in active_players() if str(p["nba_id"]) not in have]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo)} active players without a face/ photo")

    added, silhouettes = [], []
    for p in todo:
        fn = f'{p["nba_id"]}-{p["slug"]}.png'
        try:
            raw = get(PHOTO_URL.format(p["nba_id"]))
        except Exception as e:
            print(f"  {p['full_name']}: download failed ({e})")
            continue
        if len(raw) <= 5000:   # the CDN's blank silhouette (same threshold as fetch_players.py)
            silhouettes.append(p["full_name"])
            continue
        if a.dry_run:
            added.append(p)
            continue
        original = Image.open(io.BytesIO(raw))
        face, thumb = face_and_thumb(original)
        face.save(os.path.join(HS, "face", fn), "PNG", optimize=True)
        thumb.save(os.path.join(HS, "thumb", fn), "PNG", optimize=True)

        # face2 from the ORIGINAL (recrop_faces prefers it), with recrop_faces' own functions.
        tmp = os.path.join(HS, ".tmp-original.png")
        original.save(tmp)
        bgr = rc.load_bgr(tmp)
        os.remove(tmp)
        box = rc.best_face(bgr)
        f2 = rc.crop_on_face(bgr, box) if box is not None else rc.center_crop(bgr)
        cv2.imwrite(os.path.join(HS, "face2", fn), f2, [cv2.IMWRITE_PNG_COMPRESSION, 8])

        # face2-160, as make_face2_160.py does it
        Image.open(os.path.join(HS, "face2", fn)).convert("RGB").resize((160, 160), Image.LANCZOS) \
            .save(os.path.join(HS, "face2-160", fn[:-4] + ".webp"), "WEBP", quality=82, method=6)
        added.append(p)
        print(f"  added {p['full_name']} ({fn}){'' if box is not None else ' [no face found: center crop]'}")

    if added and not a.dry_run:
        for name in ("players", "active", "players_all"):
            path = os.path.join(META, f"{name}.json")
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
            known = {str(x.get("nba_id")) for x in doc["players"]}
            new = [dict(p, headshot={"face": True, "original": True, "source": "nba_cdn",
                                     "filename": f'{p["nba_id"]}-{p["slug"]}.png'})
                   for p in added if str(p["nba_id"]) not in known]
            doc["players"].extend(new)
            if "total_players" in doc:
                doc["total_players"] = len(doc["players"])
            if "with_headshot" in doc:
                doc["with_headshot"] = doc["with_headshot"] + len(new)
            # Same formatting each file already has, so the diff is only the new rows:
            # players.json and active.json escape accents, players_all.json doesn't; no final newline.
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(doc, indent=2, ensure_ascii=(name != "players_all")))

    print(f"::notice::{len(added)} players {'would be ' if a.dry_run else ''}added"
          + (f": {', '.join(p['full_name'] for p in added)}" if added else "")
          + (f". Still a silhouette on the NBA CDN: {', '.join(silhouettes)}" if silhouettes else ""))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:   # readable on the run page without opening the log
        print(f"::error::add_new_actives failed: {type(e).__name__}: {e}")
        raise

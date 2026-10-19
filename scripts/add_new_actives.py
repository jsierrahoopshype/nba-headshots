"""Add players who joined the league since the last full pipeline run (rookies, new signings).

Additive only. For every ACTIVE player in the NBA's player index who has no
players/headshots/face/ file yet, this:
  1. downloads the NBA CDN headshot (skips players whose photo is still the grey silhouette,
     judged from the pixels like build_head_uniform.py does, not from the file size),
  2. writes face/ (256px, transparent background) and thumb/ (64px), locked onto the detected
     face so heads match the existing face/ crops (the original fixed crop is the fallback),
  3. writes face2/ (520px) with recrop_faces.py's own functions, so the framing matches
     every other face2 crop,
  4. writes face2-160/ (160px WebP) like make_face2_160.py,
  5. appends the player to players.json, active.json and players_all.json.
Then it keeps the "active" flag in step with the index: a player the index no longer lists as
active gets "active": false in players.json and players_all.json and leaves active.json (the
active-only view, as build_index.py writes it); a player who comes back is flipped to true, gets
the team the index lists now, and is put back in active.json. Nobody is deleted from players.json or players_all.json and no image
file is touched by this step. It is skipped when the index lists fewer than MIN_INDEX_ACTIVE
active players (a broken or partial download must not deactivate the league).
Existing files and existing metadata rows are never touched, with one exception: an active
player whose face/ file is the CDN's grey silhouette (committed before the pixel check existed)
is downloaded again, and once the CDN has a real photo their face/, thumb/, face2/ and face2-160/
files are replaced under the same filename. face-tight/, head-uniform/ and head-uniform-480/ are
built afterwards by their own scripts (the workflow runs them).

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


# face/ framing, measured on existing face/ crops: the head is a bit bigger than in face2/
# (face box ~50% of the side vs 44%) and sits a touch lower. Locking onto the detected face
# keeps rookies' heads the same size as everyone else's: the CDN frames new photos wider, so
# process_faces.py's fixed 15-85% / 2-70% crop made their heads visibly smaller.
FACE_SHARE_FACE1, EYE_LINE_FACE1 = 0.50, 0.47


def face_and_thumb(original, rc):
    """face/ (256, transparent) and thumb/ (64) for one player."""
    img = remove_bg(original.convert("RGBA")).convert("RGBA")
    w, h = img.size
    import cv2
    bgr = cv2.cvtColor(np.array(Image.alpha_composite(Image.new("RGBA", img.size, (22, 22, 22, 255)), img).convert("RGB")),
                       cv2.COLOR_RGB2BGR)
    box = rc.best_face(bgr)
    if box is not None:
        fx, fy, fw, fh = box
        side = min(fh / FACE_SHARE_FACE1, w * 1.6, h * 1.6)
        x0 = fx + fw / 2.0 - side / 2.0
        y0 = fy + fh / 2.0 - side * EYE_LINE_FACE1
        canvas = Image.new("RGBA", (int(round(side)), int(round(side))), (0, 0, 0, 0))
        canvas.paste(img, (int(round(-x0)), int(round(-y0))), img)   # outside the photo stays transparent
        square = canvas
    else:   # no face found: the original recipe
        crop = img.crop((int(w * 0.15), int(h * 0.02), int(w * 0.85), int(h * 0.70)))
        cw, ch = crop.size
        side = max(cw, ch)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(crop, ((side - cw) // 2, (side - ch) // 2), crop)
    return square.resize((256, 256), Image.LANCZOS), square.resize((64, 64), Image.LANCZOS)


# A full NBA index lists ~500-650 active players (rosters plus two-way deals). Fewer than this
# means a broken download, so the active flags are left alone.
MIN_INDEX_ACTIVE = 400


def write_meta(name, doc):
    # Same formatting each file already has, so the diff is only the changed rows:
    # players.json and active.json escape accents, players_all.json doesn't; no final newline.
    with open(os.path.join(META, f"{name}.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, indent=2, ensure_ascii=(name != "players_all")))


def sync_active(actives, dry_run):
    """Set "active" from the index. Returns (deactivated, reactivated) as lists of names."""
    if len(actives) < MIN_INDEX_ACTIVE:
        print(f"::warning::index lists only {len(actives)} active players; active flags left as they are")
        return [], []
    ids = {str(p["nba_id"]) for p in actives}
    team = {str(p["nba_id"]): {"team_id": p["team_id"], "team_abbrev": p["team_abbrev"]} for p in actives}
    docs = {}
    for name in ("players", "active", "players_all"):
        with open(os.path.join(META, f"{name}.json"), encoding="utf-8") as f:
            docs[name] = json.load(f)
    off, on, changed = {}, {}, set()
    for name in ("players", "players_all"):
        for row in docs[name]["players"]:
            pid = str(row.get("nba_id"))
            if row.get("active") and pid not in ids:
                row["active"] = False
                off[pid] = row["full_name"]
                changed.add(name)
            elif row.get("active") is False and pid in ids:
                row["active"] = True
                row.update(team[pid])   # whatever team they had when they left is stale
                on[pid] = row["full_name"]
                changed.add(name)
    # active.json: drop rows the index no longer lists, put returning players back (their
    # players.json row, else players_all.json's), at the end like new players.
    act = docs["active"]
    listed = {str(r.get("nba_id")) for r in act["players"]}
    keep = [r for r in act["players"] if str(r.get("nba_id")) in ids]
    full = {str(r.get("nba_id")): r for r in docs["players_all"]["players"]}
    full.update({str(r.get("nba_id")): r for r in docs["players"]["players"]})
    back = [dict(full[pid], active=True, **team[pid]) for pid in sorted(ids - listed) if pid in full]
    for r in act["players"]:
        if str(r.get("nba_id")) not in ids:
            off[str(r.get("nba_id"))] = r["full_name"]
    for r in back:
        on[str(r["nba_id"])] = r["full_name"]
    if len(keep) != len(act["players"]) or back:
        act["players"] = keep + back
        act["total_players"] = len(act["players"])
        act["with_headshot"] = sum(1 for r in act["players"] if (r.get("headshot") or {}).get("face"))
        changed.add("active")
    if not dry_run:
        for name in changed:
            write_meta(name, docs[name])
    return sorted(off.values()), sorted(on.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--redo-face", default="", help="comma-separated NBA ids: rebuild only their face/ and thumb/")
    a = ap.parse_args()

    import cv2
    import recrop_faces as rc   # its own face2 functions (cascade, crop_on_face, center_crop)
    from build_head_uniform import is_placeholder   # pure numpy; MediaPipe is only loaded by its main()

    if a.redo_face:
        ids = {x.strip() for x in a.redo_face.split(",") if x.strip()}
        for fn in sorted(os.listdir(os.path.join(HS, "face"))):
            if fn.split("-", 1)[0] in ids:
                original = Image.open(io.BytesIO(get(PHOTO_URL.format(fn.split("-", 1)[0]))))
                face, thumb = face_and_thumb(original, rc)
                face.save(os.path.join(HS, "face", fn), "PNG", optimize=True)
                thumb.save(os.path.join(HS, "thumb", fn), "PNG", optimize=True)
                print(f"  face/ rebuilt: {fn}")
        return

    have = {f.split("-", 1)[0]: f for f in os.listdir(os.path.join(HS, "face")) if f.endswith(".png")}
    actives = active_players()
    todo = [p for p in actives if str(p["nba_id"]) not in have]
    # Active players whose face/ file is the grey silhouette: try the CDN again.
    retry = [p for p in actives if str(p["nba_id"]) in have and is_placeholder(
        Image.open(os.path.join(HS, "face", have[str(p["nba_id"])])).convert("RGBA"))]
    todo += retry
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo) - len(retry)} active players without a face/ photo, "
          f"{len(retry)} with the grey silhouette in face/")

    added, replaced, silhouettes = [], [], []
    for p in todo:
        old = have.get(str(p["nba_id"]))
        fn = old or f'{p["nba_id"]}-{p["slug"]}.png'   # a replaced photo keeps its filename
        try:
            raw = get(PHOTO_URL.format(p["nba_id"]))
        except Exception as e:
            print(f"  {p['full_name']}: download failed ({e})")
            continue
        if len(raw) <= 5000:   # the old CDN silhouette (same threshold as fetch_players.py)
            silhouettes.append(p["full_name"])
            continue
        original = Image.open(io.BytesIO(raw))
        face, thumb = face_and_thumb(original, rc)
        # The CDN's current silhouette is a bigger file than the size check above expects, so
        # test the cutout itself, with the same rule head-uniform uses to send players to initials.
        if is_placeholder(face):
            silhouettes.append(p["full_name"])
            continue
        if a.dry_run:
            (replaced if old else added).append(p)
            continue
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
        (replaced if old else added).append(p)
        print(f"  {'silhouette replaced' if old else 'added'}: {p['full_name']} ({fn})"
              f"{'' if box is not None else ' [no face found: center crop]'}")

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
            write_meta(name, doc)

    # --limit is for trying the photo steps on a few players, so it leaves the flags alone.
    deactivated, reactivated = ([], []) if a.limit else sync_active(actives, a.dry_run)

    would = "would be " if a.dry_run else ""
    print(f"::notice::{len(added)} players {would}added"
          + (f": {', '.join(p['full_name'] for p in added)}" if added else "")
          + (f". {len(replaced)} silhouettes {would}replaced by real photos: "
             f"{', '.join(p['full_name'] for p in replaced)}" if replaced else "")
          + (f". Still a silhouette on the NBA CDN: {', '.join(silhouettes)}" if silhouettes else "")
          + (f". {len(deactivated)} {would}marked inactive (no longer active in the NBA index): "
             f"{', '.join(deactivated)}" if deactivated else "")
          + (f". {len(reactivated)} {would}marked active again: {', '.join(reactivated)}" if reactivated else ""))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:   # readable on the run page without opening the log
        print(f"::error::add_new_actives failed: {type(e).__name__}: {e}")
        raise

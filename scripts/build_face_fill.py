#!/usr/bin/env python3
"""
Builds players/headshots/face-fill/<stem>.webp (160x160) and face-fill-320/<stem>.webp (320x320):
the one HoopsMatic headshot look, chosen by Jorge on Oct 26 2026 ("option C"). The face fills the
frame: eyes a little above the middle, chin just inside the bottom edge, no neck or jersey line at
the bottom and no photo background. Meant to be shown in a circle (CSS border-radius:50%) on any
background; what the cutout doesn't cover stays transparent.

Made from the head-uniform framing, which already puts every face at the same size and place:
eye line level, eye midpoint 50% across and 48% down, eyes 20% of the width apart. Sources, best
first:
  1. head-uniform-sharp/  (480px from the NBA's 1040x760 originals, never blown up)
  2. head-uniform-480/    (the same framing from the 256px face/ cutouts, for players with no
                           sharp file)
Players in neither (no NBA photo, photo with a solid background, profile shots, failed
landmarks) or in MANUAL_EXCLUDE get no file and are listed in face-fill/MISSING.md: show initials
for them.

The crop, in head-uniform pixels at 480: a square SIDE_EYES eye-distances wide (340px when the
eyes are 96px apart), centred on the eye midpoint across, with the eye line EYE_Y of the way
down. Photos head-uniform shrank to keep tall hair in frame ("lifted", about 150) have their eyes
lower and closer together; their own eye position and eye distance (worked out from the chin,
which the shrink keeps in place) are used, so their face fills the frame like everyone else's.

face-fill/.hashes.json: stem -> {source folder, sha of the source record, crop}. Reruns only redo
players whose source changed; changing RECIPE redoes everyone.

Run from the repo root:
    python scripts/build_face_fill.py            # incremental
    python scripts/build_face_fill.py --force    # rebuild everything
Additive only: reads head-uniform-sharp/ and head-uniform-480/, writes face-fill/ and
face-fill-320/. Never touches anything else. Needs: pip install pillow
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HS = os.path.join(ROOT, "players", "headshots")
SOURCES = ["head-uniform-sharp", "head-uniform-480"]  # best first
OUT = {160: os.path.join(HS, "face-fill"), 320: os.path.join(HS, "face-fill-320")}
STATE = os.path.join(OUT[160], ".hashes.json")
MISSING = os.path.join(OUT[160], "MISSING.md")

FRAME = 480          # head-uniform frame size
EYE_DIST = 0.20      # head-uniform: eye distance as a share of the frame
EYE_Y0 = 0.48        # head-uniform: eye line, share of the frame from the top
SIDE_EYES = 340 / 96  # crop side in eye distances (option C: 340px at 96px eye distance)
EYE_Y = 0.40         # eye line in the crop, share of the side from the top
# Source files that pass head-uniform's checks but are wrong at this size (show initials):
# 1460-james-worthy: a profile shot blown up 3x in head-uniform-480.
MANUAL_EXCLUDE = {"1460-james-worthy"}
QUALITY = 82
RECIPE = f"fill-v2 side={SIDE_EYES:.4f} eye_y={EYE_Y} q={QUALITY}"


def load_records(folder):
    p = os.path.join(HS, folder, ".sources.json" if folder.endswith("sharp") else ".hashes.json")
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        d = json.load(f)
    return d.get("files", d)


def crop_box(rec):
    """(left, top, side) in head-uniform pixels for one record."""
    # "lifted" records give the eye line as a share of the frame height (0.49), not in pixels
    eye_y = rec.get("eye_y", EYE_Y0) * FRAME
    k = 1.0
    if rec.get("lifted"):
        # shrunk about the chin: the eye-to-chin distance shrank by the same factor
        chin = rec["chin"]
        k = (chin - eye_y) / (chin - EYE_Y0 * FRAME)
    side = SIDE_EYES * EYE_DIST * FRAME * k
    return FRAME / 2 - side / 2, eye_y - EYE_Y * side, side


def render(job):
    stem, folder, rec, key, outs = job
    left, top, side = crop_box(rec)
    im = Image.open(os.path.join(HS, folder, stem + ".webp")).convert("RGBA")
    # crop() pads with transparency if the box ever runs past the frame
    sq = im.crop((round(left), round(top), round(left + side), round(top + side)))
    for n, p in outs.items():
        sq.resize((n, n), Image.LANCZOS).save(p, "WEBP", quality=QUALITY, method=4)
    return stem, key, [round(left, 1), round(top, 1), round(side, 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="rebuild everything")
    args = ap.parse_args()
    for d in OUT.values():
        os.makedirs(d, exist_ok=True)
    state = {} if args.force or not os.path.exists(STATE) else json.load(open(STATE))
    if state.get("recipe") != RECIPE:
        state = {"recipe": RECIPE, "files": {}}
    done = state["files"]
    recs = {s: load_records(s) for s in SOURCES}
    stems = sorted(f[:-4] for f in os.listdir(os.path.join(HS, "face")) if f.endswith(".png"))
    wrote = kept = 0
    missing = []
    todo = []
    for stem in stems:
        src = None
        for s in ([] if stem in MANUAL_EXCLUDE else SOURCES):
            r = recs[s].get(stem)
            if r and r.get("status") == "ok" and os.path.exists(os.path.join(HS, s, stem + ".webp")):
                src = (s, r)
                break
        outs = {n: os.path.join(d, stem + ".webp") for n, d in OUT.items()}
        if src is None:
            for p in outs.values():
                if os.path.exists(p):
                    os.remove(p)
            done.pop(stem, None)
            why = "MANUAL_EXCLUDE in build_face_fill.py" if stem in MANUAL_EXCLUDE else next(
                (recs[s][stem].get("reason") for s in SOURCES if stem in recs[s] and recs[s][stem].get("reason")),
                "no head-uniform file")
            missing.append((stem, why))
            continue
        folder, rec = src
        key = {"src": folder, "sha": rec["sha"]}
        if done.get(stem, {}).get("src") == folder and done[stem].get("sha") == rec["sha"] and all(map(os.path.exists, outs.values())):
            kept += 1
            continue
        todo.append((stem, folder, rec, key, outs))
    with cf.ProcessPoolExecutor() as ex:
        for stem, key, box in ex.map(render, todo, chunksize=8):
            done[stem] = dict(key, box=box)
            wrote += 1
    with open(STATE, "w") as f:
        json.dump(state, f, indent=0, sort_keys=True)
        f.write("\n")
    with open(MISSING, "w") as f:
        f.write("# face-fill: players with no file (show initials)\n\n"
                "Written by scripts/build_face_fill.py. They have no head-uniform-sharp or "
                "head-uniform-480 file, so no face-fill either.\n\n")
        for stem, why in missing:
            f.write(f"- {stem}: {why}\n")
    print(f"face-fill: {wrote} written, {kept} unchanged, {len(missing)} without a source (initials)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

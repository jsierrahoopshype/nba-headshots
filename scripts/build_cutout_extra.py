#!/usr/bin/env python3
"""
Builds players/headshots/cutout-extra/: background-removed cut-outs for the few players whose
only photo still has its studio or arena background, so they can get a face-fill headshot too.

Added Oct 28 2026 for four legends who showed initials everywhere (their face/ and face2/
photos are opaque, so head-uniform excluded them with "no transparency"):
    467-jason-kidd, 77141-dennis-johnson, 77480-slater-martin, 920-ac-green

Per stem in STEMS:
  1. cut the background out of face2/<stem>.png (520px, the biggest copy in the repo) with rembg
     (MIT) and its u2net model (Apache-2.0), run locally, with rembg's alpha matting (pymatting, MIT)
     for the edges; no paid service, no key. Only the largest opaque blob is kept (stray specks
     of background are dropped).
  2. save it as cutout-extra/<stem>.png (the new source file, 520x520 RGBA).
  3. frame it exactly like head-uniform-480/ (scripts/build_head_uniform.py's frame() at 480:
     MediaPipe eye landmarks, eye line level, eyes 20% of the width apart at 50%/48%, the same
     hair-at-the-top fix) and save cutout-extra/<stem>.webp plus its record in
     cutout-extra/.hashes.json (same fields as head-uniform-480/.hashes.json).
scripts/build_face_fill.py reads cutout-extra/ as its third source (after head-uniform-sharp and
head-uniform-480), so these players get face-fill/ and face-fill-320/ files framed like everyone.

Steps 1-2 are run by hand when a player is added to STEMS (rembg is not needed anywhere else);
step 3 is incremental and also runs in .github/workflows/cutout-extra.yml when a cut-out changes.
Run from the repo root:
    python scripts/build_cutout_extra.py --cut   # steps 1-3: pip install "rembg[cpu]" too
    python scripts/build_cutout_extra.py         # step 3 only
Additive only: reads face2/, writes cutout-extra/. Never touches anything else.
Needs: pip install pillow numpy scipy "mediapipe==1.1.1"
(rembg downloads u2net.onnx once from its GitHub releases to ~/.u2net.)
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.chdir(ROOT)
import build_head_uniform as hu  # noqa: E402

hu.SIZE = 480  # the recipe's functions read SIZE when they run (as build_head_uniform_480 does)
SRC = os.path.join("players", "headshots", "face2")
DST = os.path.join("players", "headshots", "cutout-extra")
HASHES = os.path.join(DST, ".hashes.json")
MODEL = "u2net"
QUALITY = 90
RECIPE = 1          # bump to reframe every cut-out
STEMS = [
    "467-jason-kidd",
    "77141-dennis-johnson",
    "77480-slater-martin",
    "920-ac-green",
]


def keep_largest_blob(im):
    """Zero the alpha of everything not connected to the biggest opaque region."""
    from scipy import ndimage  # comes with rembg's dependencies
    a = np.array(im)
    lab, n = ndimage.label(a[..., 3] > hu.ALPHA_MIN)
    if n > 1:
        sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
        main = 1 + int(np.argmax(sizes))
        # grow the main blob a little so its own soft edge is kept
        keep = ndimage.binary_dilation(lab == main, iterations=3)
        a[..., 3] = np.where(keep, a[..., 3], 0)
    return Image.fromarray(a, "RGBA")


def sha256_of(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def cut():
    """Step 1 (by hand, on a machine with rembg): face2/<stem>.png -> cutout-extra/<stem>.png."""
    from rembg import new_session, remove
    os.makedirs(DST, exist_ok=True)
    session = new_session(MODEL)
    for stem in STEMS:
        with Image.open(os.path.join(SRC, stem + ".png")) as raw:
            photo = raw.convert("RGB")
        # alpha matting (pymatting, MIT) refines the mask edge: no dark rim from the old background
        out = remove(photo, session=session, alpha_matting=True, alpha_matting_foreground_threshold=240,
                     alpha_matting_background_threshold=10, alpha_matting_erode_size=10)
        out = keep_largest_blob(out.convert("RGBA"))
        out.save(os.path.join(DST, stem + ".png"), "PNG", optimize=True)
        print(f"cut: {stem}")


def frame():
    """Step 2 (incremental, also run by .github/workflows/cutout-extra.yml): frame each cut-out
    like head-uniform-480 -> cutout-extra/<stem>.webp + .hashes.json. Players whose cut-out
    hasn't changed since their record was written are left alone."""
    store = {}
    if os.path.exists(HASHES):
        with open(HASHES, encoding="utf-8") as f:
            store = json.load(f)
    records = store.get("files", {}) if store.get("recipe") == RECIPE else {}
    lm = detect = None
    try:
        for stem in sorted(f[:-4] for f in os.listdir(DST) if f.endswith(".png")):
            png = os.path.join(DST, stem + ".png")
            out = os.path.join(DST, stem + ".webp")
            sha = sha256_of(png)
            r = records.get(stem)
            if r and r.get("sha") == sha and (r["status"] != "ok" or os.path.exists(out)):
                continue
            if detect is None:
                lm, detect = hu.make_landmarker()
            with Image.open(png) as raw:
                img, rec = hu.frame(raw.convert("RGBA"), detect)
            rec["sha"] = sha
            records[stem] = rec
            if img is None:
                if os.path.exists(out):
                    os.remove(out)
                print(f"frame: {stem}: no file ({rec['reason']})")
            else:
                img.save(out, "WEBP", quality=QUALITY, method=4, exact=False)
                print(f"frame: {stem}: ok {rec}")
    finally:
        if lm is not None:
            lm.close()
    with open(HASHES, "w", encoding="utf-8") as f:
        json.dump({"recipe": RECIPE, "files": dict(sorted(records.items()))}, f,
                  indent=0, sort_keys=True, separators=(",", ":"))
        f.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cut", action="store_true", help="redo the background removal first (needs rembg)")
    args = ap.parse_args()
    if args.cut:
        cut()
    frame()


if __name__ == "__main__":
    main()

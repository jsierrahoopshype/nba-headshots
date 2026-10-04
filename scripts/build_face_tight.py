#!/usr/bin/env python3
"""
Builds players/headshots/face-tight/<stem>.webp from players/headshots/face/<stem>.png.

face/ is the 256x256 transparent crop, but the head only fills part of the frame and the
amount of empty space varies per player. This writes a "tight" 128px WebP (with alpha) where
the opaque content is square-cropped with ~7.5% padding on each side, so heads render at a
consistent size when shown small (chips, tables, tooltips).

Per source PNG:
  1. bounding box of pixels with alpha > 16
  2. square centred on that box, side = 1.15 * max(box w, box h); the square is clamped to
     the image and padded with transparent pixels where it overflows the edge
  3. resize to 128x128 (Lanczos), save as WebP quality 90 with alpha

players/headshots/face-tight/.hashes.json maps stem -> sha256 of the source PNG, so reruns
only process new or changed sources. Sources with no opaque pixels are skipped and logged.

Run from the repo root:
    python scripts/build_face_tight.py            # incremental
    python scripts/build_face_tight.py --force    # rebuild everything
Additive only: never touches face/, face2/, face2-160/, thumb/ or the metadata.
Needs Pillow (pip install pillow).
"""
import argparse
import hashlib
import json
import os
import sys

from PIL import Image

SRC = os.path.join("players", "headshots", "face")
DST = os.path.join("players", "headshots", "face-tight")
HASHES = os.path.join(DST, ".hashes.json")
SIZE = 128
ALPHA_MIN = 16      # pixels at or below this alpha are treated as empty
PAD_FACTOR = 1.15   # square side relative to the larger bbox dimension
QUALITY = 90


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tight_crop(im):
    """Return the 128x128 RGBA tight crop, or None when the image has no opaque pixels."""
    im = im.convert("RGBA")
    # point() maps alpha > ALPHA_MIN to 255 and the rest to 0; getbbox() on that mask
    # gives the opaque bounding box as (left, top, right, bottom), right/bottom exclusive.
    mask = im.getchannel("A").point(lambda a: 255 if a > ALPHA_MIN else 0)
    box = mask.getbbox()
    if box is None:
        return None
    left, top, right, bottom = box
    bw, bh = right - left, bottom - top
    side = int(round(PAD_FACTOR * max(bw, bh)))
    cx = (left + right) / 2.0
    cy = (top + bottom) / 2.0
    x0 = int(round(cx - side / 2.0))
    y0 = int(round(cy - side / 2.0))
    # Pillow's crop() pads with transparent black wherever the box overflows the image,
    # which is exactly the "clamp to image, pad with transparent pixels" behaviour we want.
    sq = im.crop((x0, y0, x0 + side, y0 + side))
    return sq.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="rebuild even if the source hash is unchanged")
    args = ap.parse_args()

    if not os.path.isdir(SRC):
        sys.exit("run this from the nba-headshots repo root (players/headshots/face not found)")
    os.makedirs(DST, exist_ok=True)

    hashes = {}
    if os.path.exists(HASHES):
        with open(HASHES, encoding="utf-8") as f:
            hashes = json.load(f)

    written = unchanged = 0
    skipped = []
    for fname in sorted(os.listdir(SRC)):
        if not fname.lower().endswith(".png"):
            continue
        stem = fname[:-4]
        src = os.path.join(SRC, fname)
        out = os.path.join(DST, stem + ".webp")
        digest = sha256_of(src)
        if not args.force and hashes.get(stem) == digest and os.path.exists(out):
            unchanged += 1
            continue
        with Image.open(src) as im:
            result = tight_crop(im)
        if result is None:
            print(f"skip (no opaque pixels): {fname}")
            skipped.append(stem)
            # drop any stale hash so a later fix to the source is picked up
            hashes.pop(stem, None)
            continue
        result.save(out, "WEBP", quality=QUALITY, method=6, exact=False)
        hashes[stem] = digest
        written += 1

    with open(HASHES, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(hashes.items())), f, indent=0, sort_keys=True)
        f.write("\n")

    print(f"face-tight: wrote {written}, unchanged {unchanged}, skipped {len(skipped)} -> {DST}")
    if skipped:
        print("skipped stems: " + ", ".join(skipped))


if __name__ == "__main__":
    main()

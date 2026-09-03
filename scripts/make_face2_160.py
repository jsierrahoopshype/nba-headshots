#!/usr/bin/env python3
"""
Builds players/headshots/face2-160/<name>.webp from players/headshots/face2/<name>.png.

face2/ is the uniform-framing set (every head the same size, same position) but each file is
520px and ~200-300KB, too heavy for six per question in Beat LeBron. This writes a 160px WebP
copy (about 2KB each) with identical framing, so the game cards all look the same.

Run from the root of the nba-headshots repo:
    python scripts\make_face2_160.py
Additive only: never touches face/, face2/ or thumb/. Re-running skips files already built.
Needs Pillow (pip install pillow).
"""
import os, sys
from PIL import Image

SRC = os.path.join("players", "headshots", "face2")
DST = os.path.join("players", "headshots", "face2-160")
SIZE = 160

if not os.path.isdir(SRC):
    sys.exit("run this from the nba-headshots repo root (players/headshots/face2 not found)")
os.makedirs(DST, exist_ok=True)
done = skipped = 0
for f in sorted(os.listdir(SRC)):
    if not f.lower().endswith(".png"):
        continue
    out = os.path.join(DST, f[:-4] + ".webp")
    if os.path.exists(out):
        skipped += 1
        continue
    im = Image.open(os.path.join(SRC, f)).convert("RGB")
    im = im.resize((SIZE, SIZE), Image.LANCZOS)
    im.save(out, "WEBP", quality=82, method=6)
    done += 1
print(f"wrote {done}, skipped {skipped} already built -> {DST}")

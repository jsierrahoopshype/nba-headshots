#!/usr/bin/env python3
"""
Builds players/headshots/head-uniform-480/<stem>.webp: the head-uniform framing at 480x480.

Same recipe as scripts/build_head_uniform.py (it runs that script's code with a bigger frame):
MediaPipe landmarks on the face/ cutout, eye line level, distance between the eye centres 20% of
the width, eye midpoint 50% across and 48% down, WebP with a transparent background. The same
players are excluded (placeholders, opaque sources, no landmarks, profile shots, MANUAL_EXCLUDE),
so a player has a head-uniform-480 file exactly when they have a head-uniform file.

The face/ cutouts are 256x256, so a 480 frame scales them up about 2.3x (median). Rebuilding
face/ from the 1040x760 originals would give these files their full resolution.

head-uniform-480/.hashes.json keeps per-file results so reruns only process new or changed
sources; head-uniform-480/FALLBACKS.md lists the players that get initials.

Run from the repo root:
    python scripts/build_head_uniform_480.py            # incremental
    python scripts/build_head_uniform_480.py --force    # rebuild everything
Additive only: reads face/, writes head-uniform-480/. head-uniform/ is not touched.
Needs: pip install pillow numpy "mediapipe==1.1.1"
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_head_uniform as hu  # noqa: E402

hu.SIZE = 480
hu.DST = os.path.join("players", "headshots", "head-uniform-480")
hu.HASHES = os.path.join(hu.DST, ".hashes.json")
hu.FALLBACKS_MD = os.path.join(hu.DST, "FALLBACKS.md")

if __name__ == "__main__":
    hu.main()

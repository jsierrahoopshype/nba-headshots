"""Process player headshots: remove background, crop face, create thumbnails."""

import argparse
import os

import numpy as np
from PIL import Image

from utils import log

ORIGINAL_DIR = os.path.join("players", "headshots", "original")
FACE_DIR = os.path.join("players", "headshots", "face")
THUMB_DIR = os.path.join("players", "headshots", "thumb")

# Try to import rembg for better background removal
USE_REMBG = False
try:
    from rembg import remove as rembg_remove
    USE_REMBG = True
    log("rembg available — using AI background removal")
except ImportError:
    log("rembg not available — using color-key fallback")


def remove_bg_colorkey(img):
    """Remove NBA grey background using color-key method."""
    rgba = np.array(img.convert("RGBA"))
    r, g, b = rgba[:, :, 0], rgba[:, :, 1], rgba[:, :, 2]
    # NBA headshots have a grey background where R≈G≈B and values are high
    mask = (np.abs(r.astype(int) - g.astype(int)) < 35) & \
           (np.abs(g.astype(int) - b.astype(int)) < 35) & \
           (r > 160)
    rgba[mask, 3] = 0
    return Image.fromarray(rgba)


def remove_bg(img):
    """Remove background using rembg or fallback."""
    if USE_REMBG:
        return rembg_remove(img)
    return remove_bg_colorkey(img)


def crop_face(img):
    """Crop to face region: left=15%, right=85%, top=2%, bottom=70%."""
    w, h = img.size
    left = int(w * 0.15)
    right = int(w * 0.85)
    top = int(h * 0.02)
    bottom = int(h * 0.70)
    return img.crop((left, top, right, bottom))


def process_player(fname, new_only=False):
    """Process a single player headshot by filename (e.g. 2544-lebron-james.png)."""
    src = os.path.join(ORIGINAL_DIR, fname)
    face_out = os.path.join(FACE_DIR, fname)
    thumb_out = os.path.join(THUMB_DIR, fname)

    if not os.path.exists(src):
        return False

    if new_only and os.path.exists(face_out):
        return True

    try:
        img = Image.open(src).convert("RGBA")
        img = remove_bg(img)
        img = crop_face(img)

        # Face: 256x256
        face = img.resize((256, 256), Image.LANCZOS)
        face.save(face_out, "PNG")

        # Thumb: 64x64
        thumb = img.resize((64, 64), Image.LANCZOS)
        thumb.save(thumb_out, "PNG")

        return True
    except Exception as e:
        log(f"Error processing {fname}: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process player headshots into face crops and thumbnails")
    parser.add_argument("--new-only", action="store_true", help="Skip existing face PNGs")
    parser.add_argument("--id", type=int, default=None, help="Process a single player by NBA ID (finds file by prefix)")
    args = parser.parse_args()

    os.makedirs(FACE_DIR, exist_ok=True)
    os.makedirs(THUMB_DIR, exist_ok=True)

    if args.id:
        # Find file by ID prefix
        prefix = f"{args.id}-"
        matches = [f for f in os.listdir(ORIGINAL_DIR) if f.startswith(prefix) and f.endswith(".png")]
        if matches:
            ok = process_player(matches[0], new_only=args.new_only)
            log(f"Player {args.id} ({matches[0]}): {'OK' if ok else 'FAILED'}")
        else:
            log(f"Player {args.id}: no file found with prefix {prefix}")
    else:
        files = [f for f in os.listdir(ORIGINAL_DIR) if f.endswith(".png")]
        log(f"Processing {len(files)} headshots...")
        success = 0
        for i, fname in enumerate(files):
            if process_player(fname, new_only=args.new_only):
                success += 1
            if (i + 1) % 100 == 0:
                log(f"Progress: {i + 1}/{len(files)} (success={success})")
        log(f"Done. {success}/{len(files)} processed successfully")

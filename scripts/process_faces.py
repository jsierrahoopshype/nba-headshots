"""Process player headshots: remove background, crop face, create thumbnails."""

import argparse
import os
import re

import numpy as np
from PIL import Image

from utils import log

ORIGINAL_DIR = os.path.join("players", "headshots", "original")
FACE_DIR = os.path.join("players", "headshots", "face")
THUMB_DIR = os.path.join("players", "headshots", "thumb")

try:
    from rembg import remove
    import onnxruntime
    USE_REMBG = True
    print("[info] rembg loaded successfully")
except ImportError as e:
    USE_REMBG = False
    print(f"[info] rembg not available ({e}), using color-key fallback")


def remove_grey_background(img):
    """Remove NBA CDN grey background using tight color-key threshold."""
    img_rgba = img.convert("RGBA")
    data = np.array(img_rgba)
    r = data[:, :, 0].astype(int)
    g = data[:, :, 1].astype(int)
    b = data[:, :, 2].astype(int)
    # Only remove pixels that are light grey (NBA CDN background ~RGB 200-215)
    # Tight threshold to avoid removing face pixels
    grey_mask = (
        (np.abs(r - g) < 15) &
        (np.abs(g - b) < 15) &
        (np.abs(r - b) < 15) &
        (r > 185)
    )
    data[:, :, 3] = np.where(grey_mask, 0, 255)
    return Image.fromarray(data)


def remove_bg(img):
    """Remove background using rembg or fallback."""
    if USE_REMBG:
        return remove(img)
    return remove_grey_background(img)


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


def cleanup_legacy_filenames():
    """Delete PNGs named with only a numeric ID (no slug) from face and thumb dirs."""
    numeric_re = re.compile(r"^\d+\.png$")
    total_deleted = 0
    for d in (FACE_DIR, THUMB_DIR):
        if not os.path.isdir(d):
            continue
        deleted = 0
        for fname in os.listdir(d):
            if numeric_re.match(fname):
                os.remove(os.path.join(d, fname))
                deleted += 1
        if deleted:
            log(f"Deleted {deleted} legacy numeric-only file(s) from {d}")
        total_deleted += deleted
    if total_deleted == 0:
        log("No legacy numeric-only files found")
    return total_deleted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process player headshots into face crops and thumbnails")
    parser.add_argument("--new-only", action="store_true", help="Skip existing face PNGs")
    parser.add_argument("--force", action="store_true", help="Reprocess all files, overwriting existing outputs")
    parser.add_argument("--id", type=int, default=None, help="Process a single player by NBA ID (finds file by prefix)")
    parser.add_argument("--cleanup", action="store_true", help="Remove legacy numeric-only filenames from face/thumb dirs")
    args = parser.parse_args()

    os.makedirs(FACE_DIR, exist_ok=True)
    os.makedirs(THUMB_DIR, exist_ok=True)

    skip_existing = args.new_only and not args.force

    if args.cleanup:
        cleanup_legacy_filenames()
    elif args.id:
        # Find file by ID prefix
        prefix = f"{args.id}-"
        matches = [f for f in os.listdir(ORIGINAL_DIR) if f.startswith(prefix) and f.endswith(".png")]
        if matches:
            ok = process_player(matches[0], new_only=skip_existing)
            log(f"Player {args.id} ({matches[0]}): {'OK' if ok else 'FAILED'}")
        else:
            log(f"Player {args.id}: no file found with prefix {prefix}")
    else:
        files = [f for f in os.listdir(ORIGINAL_DIR) if f.endswith(".png")]
        log(f"Processing {len(files)} headshots (force={args.force})...")
        success = 0
        for i, fname in enumerate(files):
            if process_player(fname, new_only=skip_existing):
                success += 1
            if (i + 1) % 100 == 0:
                log(f"Progress: {i + 1}/{len(files)} (success={success})")
        log(f"Done. {success}/{len(files)} processed successfully")
        cleanup_legacy_filenames()

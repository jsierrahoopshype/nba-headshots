"""Process player headshots: remove background, crop face, create thumbnails."""

import argparse
import os
import re
from pathlib import Path

import numpy as np
from PIL import Image

from utils import log

ORIGINAL_DIR = Path("players") / "headshots" / "original"
FACE_DIR = Path("players") / "headshots" / "face"
THUMB_DIR = Path("players") / "headshots" / "thumb"

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


def crop_to_face(img):
    w, h = img.size
    left = int(w * 0.12)
    right = int(w * 0.88)
    top = int(h * 0.02)
    bottom = int(h * 0.62)
    return img.crop((left, top, right, bottom))


def process_player(nba_id, slug, force=False):
    src = ORIGINAL_DIR / f"{nba_id}-{slug}.png"
    dst_face = FACE_DIR / f"{nba_id}-{slug}.png"
    dst_thumb = THUMB_DIR / f"{nba_id}-{slug}.png"
    if not src.exists():
        return "no_source"
    if dst_face.exists() and not force:
        return "cached"
    img = Image.open(src)

    # Step 1: crop to face region first
    cropped = crop_to_face(img)

    # Step 2: remove background from cropped image
    if USE_REMBG:
        result = remove(cropped)
    else:
        result = remove_grey_background(cropped)

    # Step 3: resize to 256x256
    face = result.resize((256, 256), Image.LANCZOS)
    face.save(dst_face, "PNG", optimize=True)

    thumb = result.resize((64, 64), Image.LANCZOS)
    thumb.save(dst_thumb, "PNG", optimize=True)

    return "done"


def parse_filename(fname):
    """Parse 'nba_id-slug.png' into (nba_id, slug)."""
    stem = fname.rsplit(".", 1)[0]
    nba_id, slug = stem.split("-", 1)
    return int(nba_id), slug


def cleanup_legacy_filenames():
    """Delete PNGs named with only a numeric ID (no slug) from face and thumb dirs."""
    numeric_re = re.compile(r"^\d+\.png$")
    total_deleted = 0
    for d in (FACE_DIR, THUMB_DIR):
        if not d.is_dir():
            continue
        deleted = 0
        for f in d.iterdir():
            if numeric_re.match(f.name):
                f.unlink()
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

    FACE_DIR.mkdir(parents=True, exist_ok=True)
    THUMB_DIR.mkdir(parents=True, exist_ok=True)

    force = args.force or not args.new_only

    if args.cleanup:
        cleanup_legacy_filenames()
    elif args.id:
        # Find file by ID prefix
        prefix = f"{args.id}-"
        matches = [f.name for f in ORIGINAL_DIR.iterdir() if f.name.startswith(prefix) and f.name.endswith(".png")]
        if matches:
            nba_id, slug = parse_filename(matches[0])
            result = process_player(nba_id, slug, force=force)
            log(f"Player {args.id} ({matches[0]}): {result}")
        else:
            log(f"Player {args.id}: no file found with prefix {prefix}")
    else:
        files = [f.name for f in ORIGINAL_DIR.iterdir() if f.name.endswith(".png")]
        log(f"Processing {len(files)} headshots (force={args.force})...")
        success = 0
        for i, fname in enumerate(files):
            nba_id, slug = parse_filename(fname)
            result = process_player(nba_id, slug, force=force)
            if result == "done":
                success += 1
            if (i + 1) % 100 == 0:
                log(f"Progress: {i + 1}/{len(files)} (success={success})")
        log(f"Done. {success}/{len(files)} processed successfully")
        cleanup_legacy_filenames()

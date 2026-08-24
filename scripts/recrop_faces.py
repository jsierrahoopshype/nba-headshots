"""Re-crop every player headshot to identical face framing.

The problem: NBA CDN photos are framed tight on modern players and wide on
older ones, and the repo's two crop pipelines (the original 572 and the
1,213-player historical backfill) differ too — so heads render big or small
depending on era. This script normalizes ALL of them at the source:

  1. For each player image (original/ preferred, face/ as fallback), detect
     the face with OpenCV's bundled frontal-face model.
  2. Crop a square centered on the face, sized so every head occupies the
     same share of the frame (face height ~= 44% of the crop, eyes a touch
     above center) and save 520x520 into players/headshots/face2/ — a NEW
     folder, nothing existing is touched.
  3. Images where no face is found get a plain center-crop copy, so face2/
     always has every player.

Consumers then switch to face2/ (with face/ fallback) and heads match.

One-time setup:   pip install opencv-python
Run from the repo root:   python scripts/recrop_faces.py
Safe to re-run: existing face2/ files are skipped.
"""

import os
import sys

try:
    import cv2
    import numpy as np
except ImportError:
    print("OpenCV missing. Run:  pip install opencv-python")
    sys.exit(1)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACE_DIR = os.path.join(REPO_ROOT, "players", "headshots", "face")
ORIGINAL_DIR = os.path.join(REPO_ROOT, "players", "headshots", "original")
OUT_DIR = os.path.join(REPO_ROOT, "players", "headshots", "face2")
os.makedirs(OUT_DIR, exist_ok=True)

OUT_SIZE = 520
FACE_SHARE = 0.44   # face height as a share of the output side — the uniformity knob
EYE_LINE = 0.44     # face center sits at this vertical share (slightly above middle)

cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def load_bgr(path):
    """Read possibly-transparent PNGs onto a dark backdrop (repo images have alpha)."""
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 3 and img.shape[2] == 4:
        alpha = img[:, :, 3:4].astype(np.float32) / 255.0
        rgb = img[:, :, :3].astype(np.float32)
        back = np.full_like(rgb, 22.0)  # near-black, matches the game's dark UI
        img = (rgb * alpha + back * (1 - alpha)).astype(np.uint8)
    return img


def best_face(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5,
                                     minSize=(img.shape[0] // 8, img.shape[0] // 8))
    if len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])  # largest


def crop_on_face(img, face):
    h, w = img.shape[:2]
    fx, fy, fw, fh = face
    cx = fx + fw / 2.0
    cy = fy + fh / 2.0
    side = fh / FACE_SHARE
    side = min(side, w * 1.6, h * 1.6)  # never demand a wildly bigger canvas than exists
    x0 = cx - side / 2.0
    y0 = cy - side * EYE_LINE
    # Pad with the edge color when the crop reaches outside the photo.
    pad_l = max(0, int(round(-x0)))
    pad_t = max(0, int(round(-y0)))
    pad_r = max(0, int(round(x0 + side - w)))
    pad_b = max(0, int(round(y0 + side - h)))
    if pad_l or pad_t or pad_r or pad_b:
        img = cv2.copyMakeBorder(img, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_REPLICATE)
        x0 += pad_l
        y0 += pad_t
    x0, y0, s = int(round(x0)), int(round(y0)), int(round(side))
    crop = img[y0:y0 + s, x0:x0 + s]
    return cv2.resize(crop, (OUT_SIZE, OUT_SIZE), interpolation=cv2.INTER_AREA)


def center_crop(img):
    h, w = img.shape[:2]
    side = min(h, w)
    x0 = (w - side) // 2
    crop = img[0:side, x0:x0 + side]
    return cv2.resize(crop, (OUT_SIZE, OUT_SIZE), interpolation=cv2.INTER_AREA)


def main():
    names = sorted(os.listdir(FACE_DIR))
    done = detected = fallback = skipped = 0
    for i, fn in enumerate(names):
        if not fn.lower().endswith(".png"):
            continue
        out = os.path.join(OUT_DIR, fn)
        if os.path.exists(out):
            skipped += 1
            continue
        src = os.path.join(ORIGINAL_DIR, fn)
        if not os.path.exists(src):
            src = os.path.join(FACE_DIR, fn)
        img = load_bgr(src)
        if img is None:
            continue
        face = best_face(img)
        if face is not None:
            result = crop_on_face(img, face)
            detected += 1
        else:
            result = center_crop(img)
            fallback += 1
        cv2.imwrite(out, result, [cv2.IMWRITE_PNG_COMPRESSION, 8])
        done += 1
        if done % 200 == 0:
            print(f"  ...{done} written ({detected} face-locked, {fallback} center-crop)")
    print(f"Done: {done} written, {detected} face-locked, {fallback} without a detected face, {skipped} already existed.")
    print("Review a few in players/headshots/face2/, then commit and push.")


if __name__ == "__main__":
    main()

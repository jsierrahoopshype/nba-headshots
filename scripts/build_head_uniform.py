#!/usr/bin/env python3
"""
Builds players/headshots/head-uniform/<stem>.webp from players/headshots/face/<stem>.png.

Every output is a 160x160 WebP with alpha and the same framing, locked onto the detected face:
  - face box height = 45% of the frame (72px)
  - face box centred horizontally
  - top of the face box at 22% from the top (room for hair), so the chin lands around 67%
    and the neck / upper shoulders fill the bottom
  - if the hair would still poke out of the top, the whole crop moves down until it fits
    (never cut the head); the chin sits far above the bottom edge at this framing
  - wherever the scaled cutout doesn't reach a frame edge the pixels stay transparent

Face detection: OpenCV Haar cascades (bundled with opencv-python; needs opencv-python<5,
OpenCV 5 dropped CascadeClassifier). The cutout is composited onto near-black first, as
recrop_faces.py does. Three frontal cascades (default, alt2, alt) each give their largest
plausible face (sane size, upper-middle of the frame, sitting on opaque pixels):
  - two or more agree (overlap)  -> the average of the agreeing boxes
  - only one / none agree        -> the default cascade's box (else alt2, alt), but only if the
                                    face is at least 27% of the source height; a lone small box
                                    is usually a chin, an ear or a headband
  - nothing yet                  -> default cascade with minNeighbors 3, same size rule

No face found (mostly the grey placeholder silhouettes already in face/): top-anchored crop at
the median face scale. The opaque content is centred on the head (the columns of the top band)
and its top edge is put at the median hair-top line of the detected faces. Every fallback is
listed in head-uniform/FALLBACKS.md.

head-uniform/.hashes.json maps stem -> {sha256 of the source PNG, how it was framed}, so reruns
only process new or changed sources. Fallbacks are also redone when the median scale or
hair-top line drifts (new players shift the median). Changing RECIPE rebuilds everything.

Run from the repo root:
    python scripts/build_head_uniform.py            # incremental
    python scripts/build_head_uniform.py --force    # rebuild everything
Additive only: reads face/, writes head-uniform/. Never touches anything else.
Needs: pip install pillow numpy "opencv-python-headless<5"
"""
import argparse
import hashlib
import json
import os
import statistics
import sys

import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:
    sys.exit('OpenCV missing. Run:  pip install "opencv-python-headless<5"')

SRC = os.path.join("players", "headshots", "face")
DST = os.path.join("players", "headshots", "head-uniform")
HASHES = os.path.join(DST, ".hashes.json")
FALLBACKS_MD = os.path.join(DST, "FALLBACKS.md")

RECIPE = 2          # bump when the framing below changes: forces a full rebuild
SIZE = 160
FACE_SHARE = 0.45   # face box height / frame side
FACE_TOP = 0.22     # top of the face box, share of the frame from the top
HEAD_MARGIN = 1     # px kept free above the hair when the head would otherwise be cut
ALPHA_MIN = 16      # alpha at or below this counts as empty
QUALITY = 90
PAD = 512           # transparent border added around the source so any crop box fits

# Fallback defaults, used only if no face was detected anywhere (never in practice)
DEFAULT_SCALE = SIZE * FACE_SHARE / 115.0
DEFAULT_HEAD_TOP = 10.0

CASCADES = ["haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml",
            "haarcascade_frontalface_alt.xml"]
AGREE_IOU = 0.4         # two cascades "agree" when their boxes overlap at least this much
LONE_MIN_SHARE = 0.27   # a box no other cascade confirms must be at least this share of the height
_cascade_cache = {}


def cascade(name):
    if name not in _cascade_cache:
        c = cv2.CascadeClassifier(cv2.data.haarcascades + name)
        if c.empty():
            sys.exit(f"could not load {name} (opencv-python<5 is required)")
        _cascade_cache[name] = c
    return _cascade_cache[name]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def alpha_mask(im):
    return np.array(im.getchannel("A")) > ALPHA_MIN


def plausible(box, mask):
    """Reject detections that can't be the face: tiny/huge, at the frame edge, or on empty pixels."""
    x, y, w, h = box
    H, W = mask.shape
    cx, cy = x + w / 2.0, y + h / 2.0
    if not (0.22 * H <= h <= 0.70 * H):
        return False
    if not (0.20 * W <= cx <= 0.80 * W and 0.20 * H <= cy <= 0.75 * H):
        return False
    return mask[y:y + h, x:x + w].mean() >= 0.6


def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    ih = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = iw * ih
    return inter / float(aw * ah + bw * bh - inter)


def detect_face(im, mask):
    """Face box (x, y, w, h) in source pixels, or None. See the module docstring for the rules."""
    dark = Image.alpha_composite(Image.new("RGBA", im.size, (22, 22, 22, 255)), im).convert("L")
    gray = cv2.equalizeHist(np.array(dark))
    side = min(im.size)
    min_lone = LONE_MIN_SHARE * im.size[1]

    def largest(name, neighbors):
        faces = cascade(name).detectMultiScale(gray, scaleFactor=1.05, minNeighbors=neighbors,
                                               minSize=(side // 6, side // 6))
        good = [tuple(int(v) for v in f) for f in faces if plausible(f, mask)]
        return max(good, key=lambda f: f[2] * f[3]) if good else None

    boxes = [b for b in (largest(n, 5) for n in CASCADES) if b is not None]
    for anchor in boxes:   # default first, so its group wins when there are two groups
        group = [b for b in boxes if iou(anchor, b) >= AGREE_IOU]
        if len(group) >= 2:
            return tuple(int(round(v)) for v in np.mean(group, axis=0))
    for b in boxes:
        if b[3] >= min_lone:
            return b
    b = largest(CASCADES[0], 3)
    return b if b is not None and b[3] >= min_lone else None


def is_placeholder(im):
    """The grey head silhouette the NBA CDN serves when there's no photo: flat grey, no detail.
    Only solid pixels count, so a soft faded edge doesn't hide it. Labels FALLBACKS.md only."""
    a = np.array(im)
    rgb = a[..., :3][a[..., 3] > 200].astype(np.int16)
    if rgb.size == 0:
        return False
    chroma = (rgb.max(axis=1) - rgb.min(axis=1)).mean()
    return chroma < 10 and rgb.std(axis=0).mean() < 12


def render(im, scale, src_x0, src_y0):
    """160x160 crop: source pixel (src_x0, src_y0) lands on output (0, 0), at `scale` out px per src px."""
    w, h = im.size
    canvas = Image.new("RGBA", (w + 2 * PAD, h + 2 * PAD), (0, 0, 0, 0))
    canvas.paste(im, (PAD, PAD))
    span = SIZE / scale
    box = (src_x0 + PAD, src_y0 + PAD, src_x0 + PAD + span, src_y0 + PAD + span)
    # resize() premultiplies RGBA internally, so the transparent border never bleeds dark fringes
    return canvas.resize((SIZE, SIZE), Image.LANCZOS, box=box)


def frame_face(im, mask, box):
    """Returns (image, record) for a detected face."""
    fx, fy, fw, fh = box
    scale = SIZE * FACE_SHARE / fh
    src_x0 = fx + fw / 2.0 - (SIZE / 2.0) / scale
    src_y0 = fy - (SIZE * FACE_TOP) / scale
    # Hair check: topmost opaque row over the face columns. If it would land above the frame,
    # slide the crop down (the chin is ~53px from the bottom at this framing, plenty of room).
    cols = mask[:, max(fx, 0):fx + fw]
    rows = np.where(cols.any(axis=1))[0]
    head_top_out = None
    if rows.size:
        head_top_out = (rows[0] - src_y0) * scale
        if head_top_out < HEAD_MARGIN:
            src_y0 -= (HEAD_MARGIN - head_top_out) / scale
            head_top_out = HEAD_MARGIN
    rec = {"mode": "face", "face": [fx, fy, fw, fh], "scale": round(scale, 5),
           "head_top": None if head_top_out is None else round(float(head_top_out), 2)}
    return render(im, scale, src_x0, src_y0), rec


def frame_fallback(im, mask, scale, head_top):
    """Top-anchored crop at the median face scale; None when the image has no opaque pixels."""
    rows = np.where(mask.any(axis=1))[0]
    if rows.size == 0:
        return None
    top = rows[0]
    # centre on the head, not the shoulders: opaque columns in the top band (one face height)
    band = mask[top:top + int(round(SIZE * FACE_SHARE / scale))]
    cols = np.where(band.any(axis=0))[0]
    cx = (cols[0] + cols[-1] + 1) / 2.0
    src_x0 = cx - (SIZE / 2.0) / scale
    src_y0 = top - head_top / scale
    return render(im, scale, src_x0, src_y0)


def write_fallbacks_md(records, scale, head_top):
    fb = sorted(s for s, r in records.items() if r.get("mode") == "fallback")
    opaque = sorted(s for s, r in records.items() if r.get("no_alpha"))
    lines = [
        "# head-uniform fallbacks",
        "",
        "No face was detected in these face/ cutouts, so they use a top-anchored crop of the opaque",
        f"bounding box at the median face scale ({scale:.4f} output px per source px), with the top",
        f"of the cutout at the median hair-top line ({head_top:.1f}px) and the head centred.",
        "Generated by scripts/build_head_uniform.py.",
        "",
        f"Total: {len(fb)}",
        "",
        "| file | reason |",
        "|---|---|",
    ]
    for s in fb:
        reason = "placeholder silhouette" if records[s].get("placeholder") else "no face detected"
        lines.append(f"| {s}.webp | {reason} |")
    if opaque:
        lines += ["", "## Sources without alpha", "",
                  "These face/ PNGs are opaque photos (no transparent background), so their",
                  "head-uniform crop keeps the photo background.", ""]
        lines += [f"- {s}.png" for s in opaque]
    with open(FALLBACKS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="rebuild even if the source hash is unchanged")
    args = ap.parse_args()

    if not os.path.isdir(SRC):
        sys.exit("run this from the nba-headshots repo root (players/headshots/face not found)")
    os.makedirs(DST, exist_ok=True)

    store = {}
    if os.path.exists(HASHES):
        with open(HASHES, encoding="utf-8") as f:
            store = json.load(f)
    records = store.get("files", {}) if store.get("recipe") == RECIPE and not args.force else {}

    sources = sorted(f[:-4] for f in os.listdir(SRC) if f.lower().endswith(".png"))
    # sources that disappeared from face/ drop out of the index (their .webp is left alone)
    records = {s: r for s, r in records.items() if s in set(sources)}

    written = unchanged = 0
    empty = []
    pending_fallback = []   # (stem, digest, no_alpha, placeholder) framed after the median is known
    for stem in sources:
        src = os.path.join(SRC, stem + ".png")
        out = os.path.join(DST, stem + ".webp")
        digest = sha256_of(src)
        rec = records.get(stem)
        if rec and rec.get("sha") == digest and os.path.exists(out):
            if rec.get("mode") == "fallback":
                pending_fallback.append((stem, digest, rec.get("no_alpha", False), rec.get("placeholder", False)))
            else:
                unchanged += 1
            continue
        with Image.open(src) as raw:
            no_alpha = raw.mode not in ("RGBA", "LA", "PA") and "transparency" not in raw.info
            im = raw.convert("RGBA")
        mask = alpha_mask(im)
        box = detect_face(im, mask)
        if box is None:
            pending_fallback.append((stem, digest, no_alpha, is_placeholder(im)))
            continue
        result, rec = frame_face(im, mask, box)
        result.save(out, "WEBP", quality=QUALITY, method=4, exact=False)
        rec.update(sha=digest)
        if no_alpha:
            rec["no_alpha"] = True
        records[stem] = rec
        written += 1

    faces = [r for r in records.values() if r.get("mode") == "face"]
    scale = statistics.median(r["scale"] for r in faces) if faces else DEFAULT_SCALE
    tops = [r["head_top"] for r in faces if r.get("head_top") is not None]
    head_top = statistics.median(tops) if tops else DEFAULT_HEAD_TOP

    fb_written = 0
    for stem, digest, no_alpha, placeholder in pending_fallback:
        out = os.path.join(DST, stem + ".webp")
        rec = records.get(stem)
        if (rec and rec.get("mode") == "fallback" and rec.get("sha") == digest and os.path.exists(out)
                and abs(rec["scale"] - scale) / scale < 0.01 and abs(rec["head_top"] - head_top) < 0.5):
            unchanged += 1
            continue
        with Image.open(os.path.join(SRC, stem + ".png")) as raw:
            im = raw.convert("RGBA")
        result = frame_fallback(im, alpha_mask(im), scale, head_top)
        if result is None:
            print(f"skip (no opaque pixels): {stem}.png")
            empty.append(stem)
            records.pop(stem, None)
            continue
        result.save(out, "WEBP", quality=QUALITY, method=4, exact=False)
        rec = {"mode": "fallback", "sha": digest, "scale": round(scale, 5), "head_top": round(head_top, 2)}
        if no_alpha:
            rec["no_alpha"] = True
        if placeholder:
            rec["placeholder"] = True
        records[stem] = rec
        fb_written += 1

    with open(HASHES, "w", encoding="utf-8") as f:
        json.dump({"recipe": RECIPE, "files": dict(sorted(records.items()))}, f,
                  indent=0, sort_keys=True, separators=(",", ":"))
        f.write("\n")
    write_fallbacks_md(records, scale, head_top)

    n_fb = sum(1 for r in records.values() if r.get("mode") == "fallback")
    print(f"head-uniform: wrote {written} face + {fb_written} fallback, unchanged {unchanged}, "
          f"skipped {len(empty)} -> {DST}")
    print(f"  {len(faces)} detected faces, {n_fb} fallbacks; median scale {scale:.4f}, "
          f"median hair-top {head_top:.1f}px")
    if empty:
        print("skipped stems: " + ", ".join(empty))


if __name__ == "__main__":
    main()

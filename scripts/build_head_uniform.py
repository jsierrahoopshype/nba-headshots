#!/usr/bin/env python3
"""
Builds players/headshots/head-uniform/<stem>.webp from players/headshots/face/<stem>.png,
normalised like a passport photo from facial landmarks.

Per face/ cutout:
  1. MediaPipe Face Landmarker (Apache-2.0 model, 478 landmarks) on the cutout composited onto
     mid grey; retried at 2x if nothing is found. Each eye centre is the mean of its 16 contour
     landmarks, so it doesn't move with gaze the way the iris does.
  2. Rotate so the eye line is horizontal, scale so the distance between the eye centres is 25%
     of the frame width, put the eye midpoint at 50% across and 44% down.
  3. 160x160 WebP with alpha. Whatever the cutout doesn't cover stays transparent.

No file is written for the grey placeholder silhouettes, for photos where the landmarks fail,
or for profile shots (eye-to-chin over 2.6x the eye distance, where eye-based scaling blows the
face up). Any stale file for them is removed. They're listed in head-uniform/FALLBACKS.md as
"use initials", so consumers fall back to initials.

head-uniform/.hashes.json maps stem -> {sha256 of the source, result, chin/crown positions}, so
reruns only process new or changed sources. Changing RECIPE rebuilds everything.
  chin  = output y of the chin landmark (152)
  crown = output y of the top of the head (topmost opaque pixel within half an eye distance
          of the centre line), measured before clipping, so a negative value means hair is cut

The model (~3.7 MB) is downloaded once to ~/.cache/nba-headshots/ and checked against its sha256.

Run from the repo root:
    python scripts/build_head_uniform.py            # incremental
    python scripts/build_head_uniform.py --force    # rebuild everything
Additive only: reads face/, writes head-uniform/. Never touches anything else.
Needs: pip install pillow numpy "mediapipe==1.1.1"
(Linux without a desktop also needs libegl1 and libgles2 for MediaPipe's shared library.)
"""
import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import urllib.request

import numpy as np
from PIL import Image

SRC = os.path.join("players", "headshots", "face")
DST = os.path.join("players", "headshots", "head-uniform")
HASHES = os.path.join(DST, ".hashes.json")
FALLBACKS_MD = os.path.join(DST, "FALLBACKS.md")

RECIPE = 3            # bump when the framing below changes: forces a full rebuild
SIZE = 160
EYE_DIST = 0.25       # distance between eye centres / frame width
EYE_X, EYE_Y = 0.50, 0.44   # eye midpoint, share of the frame
SUPERSAMPLE = 2       # rotate/scale at 2x, then Lanczos down: sharper than one bicubic pass
QUALITY = 90
ALPHA_MIN = 16

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
MODEL_PATH = os.path.join(os.path.expanduser("~"), ".cache", "nba-headshots", "face_landmarker.task")

# MediaPipe face mesh eye contours. "Right" is the subject's right eye, on the left of the image.
RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
LEFT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
CHIN = 152

REASON_PLACEHOLDER = "placeholder silhouette"
REASON_NO_LANDMARKS = "no landmarks"
REASON_OFF_CUTOUT = "landmarks off the cutout"
REASON_PROFILE = "face turned (profile)"
# eye-line-to-chin / eye distance is ~1.8 for a frontal face (1.5-2.1 covers 99% of face/).
# Turned heads shrink the eye distance and blow the face up; above this the shot is a profile.
MAX_CHIN_RATIO = 2.6


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_model():
    if not (os.path.exists(MODEL_PATH) and sha256_of(MODEL_PATH) == MODEL_SHA256):
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        print(f"downloading face landmarker model -> {MODEL_PATH}")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH + ".part")
        if sha256_of(MODEL_PATH + ".part") != MODEL_SHA256:
            sys.exit("face landmarker model sha256 mismatch; refusing to use it")
        os.replace(MODEL_PATH + ".part", MODEL_PATH)
    return MODEL_PATH


def make_landmarker():
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mpt
        from mediapipe.tasks.python import vision
    except ImportError:
        sys.exit('MediaPipe missing. Run:  pip install "mediapipe==1.1.1"')
    opts = vision.FaceLandmarkerOptions(
        base_options=mpt.BaseOptions(model_asset_path=ensure_model()),
        running_mode=vision.RunningMode.IMAGE, num_faces=1,
        min_face_detection_confidence=0.5, min_face_presence_confidence=0.5)
    lm = vision.FaceLandmarker.create_from_options(opts)

    def detect(rgb):
        r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
        return r.face_landmarks[0] if r.face_landmarks else None
    return lm, detect


def is_placeholder(im):
    """The grey head silhouette the NBA CDN serves when there's no photo: flat grey, no detail.
    Only solid pixels count, so a soft faded edge doesn't hide it."""
    a = np.array(im)
    rgb = a[..., :3][a[..., 3] > 200].astype(np.int16)
    if rgb.size == 0:
        return True
    chroma = (rgb.max(axis=1) - rgb.min(axis=1)).mean()
    return chroma < 10 and rgb.std(axis=0).mean() < 12


def landmarks(im, detect):
    """Source-pixel landmarks as an (N, 2) array, or None. Mid-grey backdrop, then 2x if needed."""
    w, h = im.size
    flat = Image.alpha_composite(Image.new("RGBA", im.size, (128, 128, 128, 255)), im).convert("RGB")
    for up in (1, 2):
        img = flat if up == 1 else flat.resize((w * up, h * up), Image.LANCZOS)
        found = detect(np.array(img))
        if found is not None:
            return np.array([(p.x * w, p.y * h) for p in found])
    return None


def transform_for(lms):
    """(scale, angle, eye midpoint) mapping source pixels onto the output frame."""
    right = lms[RIGHT_EYE].mean(axis=0)   # image left
    left = lms[LEFT_EYE].mean(axis=0)     # image right
    dx, dy = left - right
    return SIZE * EYE_DIST / math.hypot(dx, dy), math.atan2(dy, dx), (right + left) / 2.0


def to_output(pts, scale, angle, mid):
    """Source points (N, 2) -> output points: rotate by -angle about the eye midpoint, scale, move."""
    c, s = math.cos(angle), math.sin(angle)
    d = pts - mid
    u = (c * d[:, 0] + s * d[:, 1]) * scale + SIZE * EYE_X
    v = (-s * d[:, 0] + c * d[:, 1]) * scale + SIZE * EYE_Y
    return np.stack([u, v], axis=1)


def render(im, scale, angle, mid):
    big = SIZE * SUPERSAMPLE
    k = scale * SUPERSAMPLE
    c, s = math.cos(angle), math.sin(angle)
    cx, cy = big * EYE_X, big * EYE_Y
    # Pillow wants the inverse map (output -> source): x = a*u + b*v + c0, y = d*u + e*v + f0
    a, b = c / k, -s / k
    d, e = s / k, c / k
    c0 = mid[0] - a * cx - b * cy
    f0 = mid[1] - d * cx - e * cy
    # premultiplied alpha so interpolation never drags dark fringes in from transparent pixels
    out = im.convert("RGBa").transform((big, big), Image.AFFINE, (a, b, c0, d, e, f0),
                                       resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
    return out.resize((SIZE, SIZE), Image.LANCZOS).convert("RGBA")


def frame(im, detect):
    """(image, record) for a usable photo, or (None, record with the exclusion reason)."""
    if is_placeholder(im):
        return None, {"status": "excluded", "reason": REASON_PLACEHOLDER}
    lms = landmarks(im, detect)
    if lms is None:
        return None, {"status": "excluded", "reason": REASON_NO_LANDMARKS}
    alpha = np.array(im.getchannel("A"))
    eyes = np.vstack([lms[RIGHT_EYE].mean(axis=0), lms[LEFT_EYE].mean(axis=0)])
    for x, y in eyes:
        xi, yi = int(round(x)), int(round(y))
        if not (0 <= xi < im.width and 0 <= yi < im.height) or alpha[yi, xi] <= ALPHA_MIN:
            return None, {"status": "excluded", "reason": REASON_OFF_CUTOUT}

    scale, angle, mid = transform_for(lms)
    chin = float(to_output(lms[[CHIN]], scale, angle, mid)[0, 1])
    if (chin - SIZE * EYE_Y) / (SIZE * EYE_DIST) > MAX_CHIN_RATIO:
        return None, {"status": "excluded", "reason": REASON_PROFILE}
    # crown: map every opaque source pixel to the output and take the highest one near the centre
    ys, xs = np.nonzero(alpha > ALPHA_MIN)
    pts = to_output(np.stack([xs + 0.5, ys + 0.5], axis=1), scale, angle, mid)
    near = np.abs(pts[:, 0] - SIZE * EYE_X) <= SIZE * EYE_DIST / 2.0
    crown = float(pts[near, 1].min())
    rec = {"status": "ok", "chin": round(chin, 2), "crown": round(crown, 2),
           "tilt": round(math.degrees(angle), 2), "scale": round(scale, 4)}
    return render(im, scale, angle, mid), rec


def write_fallbacks_md(records):
    ex = sorted((s, r["reason"]) for s, r in records.items() if r["status"] == "excluded")
    opaque = sorted(s for s, r in records.items() if r.get("no_alpha"))
    by_reason = {}
    for _, reason in ex:
        by_reason[reason] = by_reason.get(reason, 0) + 1
    lines = [
        "# head-uniform: use initials",
        "",
        "No head-uniform file exists for these players: their face/ cutout is a placeholder",
        "silhouette, the face landmarks could not be found, or the face is turned too far",
        "(profile) for eye-based framing. Show initials instead.",
        "Generated by scripts/build_head_uniform.py.",
        "",
        f"Total: {len(ex)} (" + ", ".join(f"{n} {r}" for r, n in sorted(by_reason.items())) + ")",
        "",
        "| player (face/ stem) | action | reason |",
        "|---|---|---|",
    ]
    lines += [f"| {s} | use initials | {reason} |" for s, reason in ex]
    if opaque:
        lines += ["", "## Written, but the source has no alpha", "",
                  "These face/ PNGs are opaque photos (no transparent background). Their head-uniform",
                  "file is written, but it keeps the photo background inside the frame.", ""]
        lines += [f"- {s}" for s in opaque]
    with open(FALLBACKS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def spread(vals):
    q = np.percentile(vals, [5, 25, 50, 75, 95])
    return (f"median {q[2]:.1f}px ({q[2] / SIZE:.1%}), IQR {q[1]:.1f}-{q[3]:.1f} "
            f"({q[3] - q[1]:.1f}px), p5-p95 {q[0]:.1f}-{q[4]:.1f}, sd {statistics.pstdev(vals):.1f}")


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
    keep = set(sources)
    records = {s: r for s, r in records.items() if s in keep}

    written = unchanged = 0
    lm = detect = None
    for stem in sources:
        src = os.path.join(SRC, stem + ".png")
        out = os.path.join(DST, stem + ".webp")
        digest = sha256_of(src)
        rec = records.get(stem)
        if rec and rec.get("sha") == digest and (rec["status"] == "excluded" or os.path.exists(out)):
            unchanged += 1
            continue
        if detect is None:
            lm, detect = make_landmarker()
        with Image.open(src) as raw:
            no_alpha = raw.mode not in ("RGBA", "LA", "PA") and "transparency" not in raw.info
            im = raw.convert("RGBA")
        result, rec = frame(im, detect)
        rec["sha"] = digest
        if no_alpha:
            rec["no_alpha"] = True
        records[stem] = rec
        if result is None:
            print(f"use initials ({rec['reason']}): {stem}")
        else:
            result.save(out, "WEBP", quality=QUALITY, method=4, exact=False)
            written += 1
    if lm is not None:
        lm.close()

    # only players with a usable photo keep a file: drop stale ones (excluded or source gone)
    wanted = {s for s, r in records.items() if r["status"] == "ok"}
    removed = 0
    for fname in os.listdir(DST):
        if fname.endswith(".webp") and fname[:-5] not in wanted:
            os.remove(os.path.join(DST, fname))
            removed += 1

    with open(HASHES, "w", encoding="utf-8") as f:
        json.dump({"recipe": RECIPE, "files": dict(sorted(records.items()))}, f,
                  indent=0, sort_keys=True, separators=(",", ":"))
        f.write("\n")
    write_fallbacks_md(records)

    ok = [r for r in records.values() if r["status"] == "ok"]
    excluded = {}
    for r in records.values():
        if r["status"] == "excluded":
            excluded[r["reason"]] = excluded.get(r["reason"], 0) + 1
    print(f"head-uniform: wrote {written}, unchanged {unchanged}, removed {removed} -> {DST}")
    print(f"  {len(ok)} files, excluded {sum(excluded.values())} "
          + (str(dict(sorted(excluded.items()))) if excluded else ""))
    if ok:
        chins = [r["chin"] for r in ok]
        crowns = [r["crown"] for r in ok]
        print(f"  chin:  {spread(chins)}; below the frame: {sum(c > SIZE for c in chins)}")
        print(f"  crown: {spread(crowns)}; hair cut at the top: {sum(c < 0 for c in crowns)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Builds players/headshots/head-uniform-sharp/<stem>.webp: the head-uniform framing at 480x480,
made from the NBA CDN's 1040x760 originals instead of the 256px face/ cutouts, and NEVER blown up.

head-uniform-480/ scales face/ cutouts up about 2.3x. This folder is new and separate: nothing
existing is read for pixels, changed or replaced (other tools use those files).

Per player in players_all.json whose headshot comes from the NBA CDN ("source": "nba_cdn"):
  1. download https://cdn.nba.com/headshots/nba/latest/1040x760/<nba id>.png (curl_cffi as
     Chrome when installed: cdn.nba.com turns plain scripts on cloud machines away). The original
     is only held in memory; nothing under players/headshots/original/ is written.
  2. the exact build_head_uniform.py recipe at 480 (same landmarks, eye line, 20% eye distance,
     50%/48% eye midpoint, hair-at-the-top fix, the same placeholder / no-transparency /
     no-landmarks / profile / MANUAL_EXCLUDE exclusions).
  3. written only when the frame needs no upscaling: the source's eyes are at least 96px apart
     (20% of 480), i.e. the output/source scale is at most 1. Otherwise no file ("too small").

Players without a file are listed in head-uniform-sharp/MISSING.md with the reason; consumers
show something else for them (hoopshype-quotes-lab: the team logo or a silhouette).
head-uniform-sharp/.sources.json: stem -> {sha256 of the original, status, reason, eye_px,
scale}, so reruns only download players not done yet (--force redoes everyone; --retry redoes
the ones that failed to download). Changing RECIPE redoes everything.

Run from the repo root:
    python scripts/build_head_uniform_sharp.py [--force] [--retry] [--limit N]
Additive only: writes head-uniform-sharp/ and nothing else.
Needs: pip install pillow numpy "mediapipe==1.1.1" "curl_cffi==0.7.*"
"""
import argparse
import concurrent.futures as cf
import hashlib
import io
import json
import os
import sys
import urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.chdir(ROOT)
import build_head_uniform as hu  # noqa: E402

hu.SIZE = 480  # the recipe's functions read SIZE when they run
DST = os.path.join("players", "headshots", "head-uniform-sharp")
SOURCES = os.path.join(DST, ".sources.json")
MISSING_MD = os.path.join(DST, "MISSING.md")
META = os.path.join("players", "metadata", "players_all.json")
PHOTO_URL = "https://cdn.nba.com/headshots/nba/latest/1040x760/{}.png"
RECIPE = 1          # bump to redo every file
QUALITY = 90
MAX_SCALE = 1.0     # output px per source px: never above 1 (no upscaling)
REASON_SMALL = "source too small for 480 (would be blown up)"
REASON_NOT_CDN = "not an NBA CDN photo"
REASON_DOWNLOAD = "download failed"


def get(url, timeout=30):
    """cdn.nba.com turns away plain scripts from cloud machines, so look like Chrome when curl_cffi is there."""
    try:
        from curl_cffi import requests as creq
    except ImportError:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.nba.com/"})
        return urllib.request.urlopen(req, timeout=timeout).read()
    r = creq.get(url, impersonate="chrome", timeout=timeout, headers={"Referer": "https://www.nba.com/"})
    r.raise_for_status()
    return r.content


def players():
    with open(META, encoding="utf-8") as f:
        j = json.load(f)
    out = []
    for p in (j if isinstance(j, list) else j.get("players", [])):
        hs = p.get("headshot") or {}
        if p.get("nba_id") and hs.get("filename"):
            out.append((os.path.splitext(hs["filename"])[0], p["nba_id"], hs.get("source")))
    return sorted(out)


def build(data, detect):
    """(image, record) or (None, record with the reason)."""
    with Image.open(io.BytesIO(data)) as raw:
        no_alpha = raw.mode not in ("RGBA", "LA", "PA") and "transparency" not in raw.info
        im = raw.convert("RGBA")
    if no_alpha:
        return None, {"status": "excluded", "reason": hu.REASON_NO_ALPHA}
    img, rec = hu.frame(im, detect)
    if img is None:
        return None, rec
    rec["eye_px"] = round(hu.SIZE * hu.EYE_DIST / rec["scale"], 1)  # eye distance in the original
    if rec["scale"] > MAX_SCALE:
        return None, {"status": "excluded", "reason": REASON_SMALL, "eye_px": rec["eye_px"], "scale": rec["scale"]}
    return img, rec


def write_missing_md(records):
    ex = sorted((s, r["reason"]) for s, r in records.items() if r["status"] != "ok")
    by = {}
    for _, reason in ex:
        by[reason] = by.get(reason, 0) + 1
    lines = ["# head-uniform-sharp: no sharp file", "",
             "No head-uniform-sharp file exists for these players: the NBA CDN original is too small",
             "for a 480 frame without blowing it up, the photo is not from the NBA CDN, or the same",
             "exclusions as head-uniform apply (placeholder, no transparency, no landmarks, profile,",
             "excluded by hand). Generated by scripts/build_head_uniform_sharp.py.", "",
             f"Total: {len(ex)} (" + ", ".join(f"{n} {r}" for r, n in sorted(by.items())) + ")", "",
             "| player (stem) | reason |", "|---|---|"]
    lines += [f"| {s} | {reason} |" for s, reason in ex]
    with open(MISSING_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="redo every player")
    ap.add_argument("--retry", action="store_true", help="redo players whose download failed")
    ap.add_argument("--limit", type=int, help="at most this many downloads (testing)")
    args = ap.parse_args()
    os.makedirs(DST, exist_ok=True)
    store = {}
    if os.path.exists(SOURCES):
        with open(SOURCES, encoding="utf-8") as f:
            store = json.load(f)
    records = store.get("files", {}) if store.get("recipe") == RECIPE and not args.force else {}
    every = players()
    known = {s for s, _, _ in every}
    records = {s: r for s, r in records.items() if s in known}

    todo = []
    for stem, nba_id, source in every:
        r = records.get(stem)
        if r and not (args.retry and r.get("reason") == REASON_DOWNLOAD) and (r["status"] != "ok" or os.path.exists(os.path.join(DST, stem + ".webp"))):
            continue
        if source != "nba_cdn":
            records[stem] = {"status": "excluded", "reason": REASON_NOT_CDN}
        elif stem in hu.MANUAL_EXCLUDE:
            records[stem] = {"status": "excluded", "reason": hu.MANUAL_EXCLUDE[stem], "manual": True}
        else:
            todo.append((stem, nba_id))
    if args.limit:
        todo = todo[:args.limit]

    def fetch(item):
        stem, nba_id = item
        for _ in range(3):
            try:
                return stem, get(PHOTO_URL.format(nba_id))
            except Exception:
                continue
        return stem, None

    written = failed = 0
    lm = detect = None
    try:
        with cf.ThreadPoolExecutor(4) as ex:
            for stem, data in ex.map(fetch, todo):
                if data is None:
                    records[stem] = {"status": "excluded", "reason": REASON_DOWNLOAD}
                    failed += 1
                    continue
                if detect is None:
                    lm, detect = hu.make_landmarker()
                try:
                    img, rec = build(data, detect)
                except Exception as e:  # an unreadable file is one player, not the run
                    img, rec = None, {"status": "excluded", "reason": f"unreadable ({type(e).__name__})"}
                rec["sha"] = hashlib.sha256(data).hexdigest()
                records[stem] = rec
                if img is not None:
                    img.save(os.path.join(DST, stem + ".webp"), "WEBP", quality=QUALITY, method=4, exact=False)
                    written += 1
    finally:
        if lm is not None:
            lm.close()
        # Only players with a sharp photo keep a file in this folder.
        wanted = {s for s, r in records.items() if r["status"] == "ok"}
        for fname in os.listdir(DST):
            if fname.endswith(".webp") and fname[:-5] not in wanted:
                os.remove(os.path.join(DST, fname))
        with open(SOURCES, "w", encoding="utf-8") as f:
            json.dump({"recipe": RECIPE, "files": dict(sorted(records.items()))}, f, indent=0, sort_keys=True, separators=(",", ":"))
            f.write("\n")
        write_missing_md(records)

    ok = [r for r in records.values() if r["status"] == "ok"]
    reasons = {}
    for r in records.values():
        if r["status"] != "ok":
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    eyes = sorted(r["eye_px"] for r in ok)
    print(f"head-uniform-sharp: downloaded {len(todo) - failed}, failed {failed}, wrote {written}; "
          f"{len(ok)} files, no file {sum(reasons.values())} {dict(sorted(reasons.items()))}")
    if eyes:
        print(f"  source eye distance of the files: min {eyes[0]:.0f}px, median {eyes[len(eyes) // 2]:.0f}px (96px = 1:1 at 480)")


if __name__ == "__main__":
    main()

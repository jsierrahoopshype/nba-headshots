#!/usr/bin/env python3
"""
Contact sheet for players/headshots/head-uniform/: N random detected faces plus every fallback,
shown on white and on dark, so the framing can be checked by eye. Small ticks on the left edge
of each tile mark the target lines: top of the face box (22%) and the chin (~67%).

    python scripts/head_uniform_contact_sheet.py                  # 20 random, seed 7
    python scripts/head_uniform_contact_sheet.py --n 40 --seed 1 --out sheet.png
Reads head-uniform/ only. Needs Pillow.
"""
import argparse
import json
import os
import random

from PIL import Image, ImageDraw

DST = os.path.join("players", "headshots", "head-uniform")
SIZE = 160
COLS = 10
GAP = 14
LABEL_H = 28
TICK = 6
BACKS = [("on white", (255, 255, 255), (40, 40, 40)), ("on dark", (22, 22, 22), (220, 220, 220))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="head-uniform-contact-sheet.png")
    a = ap.parse_args()

    with open(os.path.join(DST, ".hashes.json"), encoding="utf-8") as f:
        recs = json.load(f)["files"]
    faces = sorted(s for s, r in recs.items() if r["mode"] == "face")
    fallbacks = sorted(s for s, r in recs.items() if r["mode"] == "fallback")
    picks = sorted(random.Random(a.seed).sample(faces, min(a.n, len(faces))))
    groups = [(f"{len(picks)} random detected faces", picks), (f"all {len(fallbacks)} fallbacks", fallbacks)]

    cell_w, cell_h = SIZE + GAP + TICK, SIZE + LABEL_H
    rows_of = lambda items: (len(items) + COLS - 1) // COLS
    header = 30
    panel_h = sum(header + rows_of(items) * cell_h for _, items in groups) + header
    W = GAP + COLS * cell_w
    sheet = Image.new("RGB", (W, panel_h * len(BACKS)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)

    for p, (title, bg, fg) in enumerate(BACKS):
        y = p * panel_h
        d.rectangle([0, y, W, y + panel_h], fill=bg)
        d.text((GAP, y + 8), f"head-uniform 160px, {title}", fill=fg)
        y += header
        for gtitle, items in groups:
            d.text((GAP, y + 8), gtitle, fill=fg)
            y += header
            for i, stem in enumerate(items):
                x = GAP + TICK + (i % COLS) * cell_w
                ty = y + (i // COLS) * cell_h
                im = Image.open(os.path.join(DST, stem + ".webp")).convert("RGBA")
                sheet.paste(im, (x, ty), im)
                d.rectangle([x - 1, ty - 1, x + SIZE, ty + SIZE], outline=(128, 128, 128))
                for share in (0.22, 0.67):   # target face-top and chin lines
                    yy = ty + int(round(SIZE * share))
                    d.line([x - TICK, yy, x - 2, yy], fill=(230, 60, 60), width=2)
                d.text((x, ty + SIZE + 3), stem[:26], fill=fg)
            y += rows_of(items) * cell_h
    sheet.save(a.out, optimize=True)
    print(f"{a.out}: {len(picks)} faces + {len(fallbacks)} fallbacks, {sheet.size[0]}x{sheet.size[1]}")


if __name__ == "__main__":
    main()

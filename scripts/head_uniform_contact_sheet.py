#!/usr/bin/env python3
"""
Contact sheet for players/headshots/head-uniform/, drawn the way the files will be used: circles
at real display sizes (96px and 40px, 1:1 pixels), on a light grey (#eef0f3) and a dark
(#14161a) backdrop.

  - N random players (default 40)
  - every exception from FALLBACKS.md: the face/ source (small, for checking why it was left out)
    next to the initials circle consumers will show instead
  - a few extremes (most hair cut, smallest head, lowest chin, most tilted) for reference

The circles get a subtle fill so their edge reads where the transparent cutout doesn't reach it.

    python scripts/head_uniform_contact_sheet.py                  # 40 random, seed 7
    python scripts/head_uniform_contact_sheet.py --n 60 --seed 1 --out sheet.png
Reads face/ and head-uniform/ only. Needs Pillow and numpy.
"""
import argparse
import json
import os
import random

from PIL import Image, ImageDraw, ImageFont

SRC = os.path.join("players", "headshots", "face")
DST = os.path.join("players", "headshots", "head-uniform")
BIG, SMALL = 96, 40
COLS = 8
TILE_W, TILE_H = 196, 128
PAD = 16
THEMES = [
    ("light #eef0f3", (0xEE, 0xF0, 0xF3), (0xDC, 0xE0, 0xE6), (0x2A, 0x2E, 0x35), (0x8A, 0x90, 0x9A)),
    ("dark #14161a", (0x14, 0x16, 0x1A), (0x25, 0x28, 0x2F), (0xE6, 0xE8, 0xEC), (0x7C, 0x83, 0x8E)),
]
SS = 4   # circle masks are drawn at 4x and shrunk, for a smooth anti-aliased edge


def circle_mask(d):
    m = Image.new("L", (d * SS, d * SS), 0)
    ImageDraw.Draw(m).ellipse([0, 0, d * SS - 1, d * SS - 1], fill=255)
    return m.resize((d, d), Image.LANCZOS)


def avatar(head, d, fill):
    """head (RGBA) inside a d-px circle with a flat fill behind it."""
    disc = Image.new("RGBA", (d, d), fill + (255,))
    if head is not None:
        h = head.resize((d, d), Image.LANCZOS)
        disc.alpha_composite(h)
    disc.putalpha(circle_mask(d))
    return disc


def initials_avatar(stem, d, fill, ink):
    words = [w for w in stem.split("-", 1)[-1].split("-") if w not in ("jr", "sr", "ii", "iii", "iv")]
    text = (words[0][:1] + (words[-1][:1] if len(words) > 1 else "")).upper()
    disc = avatar(None, d, fill)
    font = font_at(int(d * 0.38))
    dr = ImageDraw.Draw(disc)
    box = dr.textbbox((0, 0), text, font=font)
    dr.text(((d - (box[2] - box[0])) / 2 - box[0], (d - (box[3] - box[1])) / 2 - box[1]),
            text, fill=ink, font=font)
    return disc


def font_at(px):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            pass
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="head-uniform-contact-sheet.png")
    a = ap.parse_args()

    with open(os.path.join(DST, ".hashes.json"), encoding="utf-8") as f:
        recs = json.load(f)["files"]
    ok = {s: r for s, r in recs.items() if r["status"] == "ok"}
    excluded = sorted((s for s, r in recs.items() if r["status"] == "excluded"),
                      key=lambda s: (recs[s]["reason"], s))
    picks = sorted(random.Random(a.seed).sample(sorted(ok), min(a.n, len(ok))))
    extremes, seen = [], set()
    for key, rev, label in [("crown", False, "most hair cut"), ("crown", True, "smallest head"),
                            ("chin", True, "lowest chin"), ("tilt", None, "most tilted")]:
        order = sorted(ok, key=lambda s: abs(ok[s][key]) if rev is None else ok[s][key], reverse=rev is not False)
        for s in order:
            if s not in seen:
                seen.add(s)
                extremes.append((s, label))
                break
        for s in order[1:]:
            if s not in seen:
                seen.add(s)
                extremes.append((s, label))
                break

    groups = [(f"{len(picks)} random players", [(s, None) for s in picks], "ok"),
              (f"all {len(excluded)} exceptions: no file, consumers show initials",
               [(s, recs[s]["reason"]) for s in excluded], "ex"),
              ("extremes, for reference", extremes, "ok")]
    rows = lambda items: (len(items) + COLS - 1) // COLS
    head_h = 34
    panel_h = head_h + sum(head_h + rows(items) * TILE_H for _, items, _ in groups) + PAD
    W = PAD * 2 + COLS * TILE_W
    sheet = Image.new("RGB", (W, panel_h * len(THEMES)))
    label_font, title_font = font_at(11), font_at(14)

    for p, (tname, bg, fill, ink, muted) in enumerate(THEMES):
        y = p * panel_h
        d = ImageDraw.Draw(sheet)
        d.rectangle([0, y, W, y + panel_h], fill=bg)
        d.text((PAD, y + 10), f"head-uniform as circles at {BIG}px and {SMALL}px, on {tname}",
               fill=ink, font=title_font)
        y += head_h
        for gtitle, items, kind in groups:
            d.text((PAD, y + 12), gtitle, fill=ink, font=label_font)
            y += head_h
            for i, (stem, note) in enumerate(items):
                x = PAD + (i % COLS) * TILE_W
                ty = y + (i // COLS) * TILE_H
                if kind == "ok":
                    head = Image.open(os.path.join(DST, stem + ".webp")).convert("RGBA")
                    big, small = avatar(head, BIG, fill), avatar(head, SMALL, fill)
                    sheet.paste(big, (x, ty), big)
                    sheet.paste(small, (x + BIG + 12, ty + BIG - SMALL), small)
                else:
                    src = Image.open(os.path.join(SRC, stem + ".png")).convert("RGBA").resize((64, 64), Image.LANCZOS)
                    sheet.paste(src, (x, ty), src)
                    big = initials_avatar(stem, BIG - 32, fill, muted)
                    small = initials_avatar(stem, SMALL, fill, muted)
                    sheet.paste(big, (x + 68, ty), big)
                    sheet.paste(small, (x + 68 + BIG - 32 + 8, ty + BIG - 32 - SMALL), small)
                name = stem.split("-", 1)[-1]
                d.text((x, ty + BIG + 4), name[:30], fill=ink, font=label_font)
                if note:
                    d.text((x, ty + BIG + 17), note, fill=muted, font=label_font)
            y += rows(items) * TILE_H
    sheet.save(a.out, optimize=True)
    print(f"{a.out}: {len(picks)} random + {len(excluded)} exceptions + {len(extremes)} extremes, "
          f"{sheet.size[0]}x{sheet.size[1]}")


if __name__ == "__main__":
    main()

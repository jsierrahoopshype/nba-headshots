#!/usr/bin/env python3
"""
Remove NBA-CDN placeholder headshots: any file in players/headshots/original/ whose bytes are
identical to 3+ other files is the CDN's generic silhouette, not a photo. Deletes that player's
original/face/face2/face2-160/thumb files and drops the record from players_all.json and
players_historical.json. Dry run by default; pass --apply to delete.
"""
import hashlib, json, os, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HS = os.path.join(ROOT, "players", "headshots")
META = os.path.join(ROOT, "players", "metadata")
ORIG = os.path.join(HS, "original")
apply = "--apply" in sys.argv

hashes = {}
for f in os.listdir(ORIG):
    if f.lower().endswith(".png"):
        hashes[f] = hashlib.md5(open(os.path.join(ORIG, f), "rb").read()).hexdigest()
counts = collections.Counter(hashes.values())
bad = sorted(f for f, h in hashes.items() if counts[h] >= 3)
print(f"{len(bad)} placeholder files found" + ("" if apply else " (dry run, add --apply to delete)"))

removed = 0
for f in bad:
    stem = f[:-4]
    for sub, name in (("original", f), ("face", f), ("face2", f), ("thumb", f), ("face2-160", stem + ".webp")):
        p = os.path.join(HS, sub, name)
        if os.path.exists(p):
            if apply:
                os.remove(p)
            removed += 1
print(f"{'removed' if apply else 'would remove'} {removed} files")

badset = set(bad)
for jf in ("players_all.json", "players_historical.json"):
    p = os.path.join(META, jf)
    if not os.path.exists(p):
        continue
    d = json.load(open(p, encoding="utf-8"))
    before = len(d["players"])
    d["players"] = [x for x in d["players"] if x.get("headshot", {}).get("filename") not in badset]
    if "total_players" in d:
        d["total_players"] = len(d["players"]); d["with_headshot"] = sum(1 for x in d["players"] if x["headshot"].get("face"))
    print(f"{jf}: {before} -> {len(d['players'])} records")
    if apply:
        json.dump(d, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

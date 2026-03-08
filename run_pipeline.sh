#!/usr/bin/env bash
set -e

echo "=== NBA Headshots Pipeline ==="
echo ""

echo "[1/6] Installing dependencies..."
pip install requests pillow numpy rembg

echo ""
echo "[2/6] Downloading player headshots from NBA CDN..."
python scripts/fetch_players.py

echo ""
echo "[3/6] Cross-referencing missing players with ESPN..."
python scripts/crosswalk_espn.py

echo ""
echo "[4/6] Processing face crops and thumbnails..."
python scripts/process_faces.py

echo ""
echo "[5/6] Downloading team logos..."
python scripts/fetch_teams.py

echo ""
echo "[6/6] Building metadata index..."
python scripts/build_index.py

echo ""
echo "=== Pipeline complete ==="
echo "Run: git add -A && git commit -m 'initial NBA asset library' && git push"

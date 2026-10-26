# NBA Headshots & Logos

NBA player headshots and team logos for [jsierrahoopshype](https://github.com/jsierrahoopshype) projects.

**GitHub Pages:** https://jsierrahoopshype.github.io/nba-headshots

## Usage (JavaScript)

```js
import NBAAssets from "https://jsierrahoopshype.github.io/nba-headshots/index.js";

const src = NBAAssets.playerFaceById(2544); // LeBron James 256x256 face
const player = await NBAAssets.playerByName("LeBron James");
```

## Usage (Python)

```python
from index import assets

path = assets.face_path(2544)        # Path to LeBron face PNG
player = assets.player_by_name("LeBron James")
```

## Running the Pipeline (Windows)

```
pip install requests pillow numpy rembg
python scripts/fetch_players.py
python scripts/crosswalk_espn.py
python scripts/process_faces.py
python scripts/fetch_teams.py
python scripts/build_index.py
```

Or on Linux/macOS: `bash run_pipeline.sh`

## Folder Structure

```
players/
  headshots/
    original/     ← full-size downloads (git-ignored)
    face/         ← 256x256 face crops (committed)
    thumb/        ← 64x64 thumbnails (committed)
    head-uniform/      ← 160x160 passport-style crops: eyes 20% of the width apart, 48% down (committed)
    head-uniform-480/  ← the same framing at 480x480, transparent WebP (committed)
    head-uniform-sharp/ ← the same framing at 480x480 made from the 1040x760 NBA CDN originals, never
                          blown up: only players whose original holds the 480 frame (committed;
                          MISSING.md lists the rest). New and separate: nothing above changes.
    face-fill/         ← THE HoopsMatic headshot (Oct 26 2026): the face fills the frame, chin just inside the
                          bottom, no neck line, no background. 160x160 transparent WebP, show it in a
                          circle. Built from head-uniform-sharp (head-uniform-480 when there's no sharp
                          file); MISSING.md lists players with neither: show initials for them.
    face-fill-320/     ← the same at 320x320, for big circles (videos, share cards)
  metadata/
    players.json  ← full player index
    active.json   ← active players only
    missing.json  ← players without headshots
    espn_crosswalk.json
teams/
  logos/
    current/
      svg/        ← team logos in SVG
      png/        ← team logos in PNG
    historical/
  metadata/
    teams.json    ← all 30 teams with metadata
fallbacks/
  player_silhouette.svg
scripts/
  utils.py
  fetch_players.py
  crosswalk_espn.py
  process_faces.py
  fetch_teams.py
  build_index.py
  build_head_uniform.py      ← head-uniform/ (160px)
  build_head_uniform_480.py  ← head-uniform-480/ (480px, same recipe)
  build_head_uniform_sharp.py ← head-uniform-sharp/ (480px from the originals, no upscaling)
  build_face_fill.py         ← face-fill/ and face-fill-320/ (weekly, .github/workflows/face-fill.yml)
index.js          ← JavaScript SDK
index.py          ← Python SDK
run_pipeline.sh   ← one-shot pipeline runner
```

## Legal

All NBA player images and team logos are property of the NBA and their respective rights holders. This repository is for internal editorial use only and is not intended for commercial redistribution. All trademarks belong to their respective owners.

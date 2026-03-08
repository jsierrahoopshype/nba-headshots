"""Download NBA team logos and build teams metadata."""

import json
import os
import shutil

from utils import log, safe_get, slugify

SVG_DIR = os.path.join("teams", "logos", "current", "svg")
PNG_DIR = os.path.join("teams", "logos", "current", "png")
METADATA_DIR = os.path.join("teams", "metadata")

LOGO_SVG_URL = "https://cdn.nba.com/logos/nba/{team_id}/global/L/logo.svg"
LOGO_PNG_URL = "https://cdn.nba.com/logos/nba/{team_id}/global/L/logo.png"

# All 30 current NBA teams with full metadata
TEAMS = [
    {"team_id": 1610612737, "slug": "atlanta-hawks", "abbrev": "ATL", "full_name": "Atlanta Hawks", "city": "Atlanta", "nickname": "Hawks", "conference": "East", "division": "Southeast", "founded": 1946, "historical_names": ["Tri-Cities Blackhawks", "Milwaukee Hawks", "St. Louis Hawks"]},
    {"team_id": 1610612738, "slug": "boston-celtics", "abbrev": "BOS", "full_name": "Boston Celtics", "city": "Boston", "nickname": "Celtics", "conference": "East", "division": "Atlantic", "founded": 1946, "historical_names": []},
    {"team_id": 1610612751, "slug": "brooklyn-nets", "abbrev": "BKN", "full_name": "Brooklyn Nets", "city": "Brooklyn", "nickname": "Nets", "conference": "East", "division": "Atlantic", "founded": 1967, "historical_names": ["New Jersey Americans", "New York Nets", "New Jersey Nets"]},
    {"team_id": 1610612766, "slug": "charlotte-hornets", "abbrev": "CHA", "full_name": "Charlotte Hornets", "city": "Charlotte", "nickname": "Hornets", "conference": "East", "division": "Southeast", "founded": 2004, "historical_names": ["Charlotte Bobcats"]},
    {"team_id": 1610612741, "slug": "chicago-bulls", "abbrev": "CHI", "full_name": "Chicago Bulls", "city": "Chicago", "nickname": "Bulls", "conference": "East", "division": "Central", "founded": 1966, "historical_names": []},
    {"team_id": 1610612739, "slug": "cleveland-cavaliers", "abbrev": "CLE", "full_name": "Cleveland Cavaliers", "city": "Cleveland", "nickname": "Cavaliers", "conference": "East", "division": "Central", "founded": 1970, "historical_names": []},
    {"team_id": 1610612742, "slug": "dallas-mavericks", "abbrev": "DAL", "full_name": "Dallas Mavericks", "city": "Dallas", "nickname": "Mavericks", "conference": "West", "division": "Southwest", "founded": 1980, "historical_names": []},
    {"team_id": 1610612743, "slug": "denver-nuggets", "abbrev": "DEN", "full_name": "Denver Nuggets", "city": "Denver", "nickname": "Nuggets", "conference": "West", "division": "Northwest", "founded": 1967, "historical_names": ["Denver Rockets"]},
    {"team_id": 1610612765, "slug": "detroit-pistons", "abbrev": "DET", "full_name": "Detroit Pistons", "city": "Detroit", "nickname": "Pistons", "conference": "East", "division": "Central", "founded": 1941, "historical_names": ["Fort Wayne Zollner Pistons", "Fort Wayne Pistons"]},
    {"team_id": 1610612744, "slug": "golden-state-warriors", "abbrev": "GSW", "full_name": "Golden State Warriors", "city": "San Francisco", "nickname": "Warriors", "conference": "West", "division": "Pacific", "founded": 1946, "historical_names": ["Philadelphia Warriors", "San Francisco Warriors"]},
    {"team_id": 1610612745, "slug": "houston-rockets", "abbrev": "HOU", "full_name": "Houston Rockets", "city": "Houston", "nickname": "Rockets", "conference": "West", "division": "Southwest", "founded": 1967, "historical_names": ["San Diego Rockets"]},
    {"team_id": 1610612754, "slug": "indiana-pacers", "abbrev": "IND", "full_name": "Indiana Pacers", "city": "Indianapolis", "nickname": "Pacers", "conference": "East", "division": "Central", "founded": 1967, "historical_names": []},
    {"team_id": 1610612746, "slug": "la-clippers", "abbrev": "LAC", "full_name": "LA Clippers", "city": "Los Angeles", "nickname": "Clippers", "conference": "West", "division": "Pacific", "founded": 1970, "historical_names": ["Buffalo Braves", "San Diego Clippers"]},
    {"team_id": 1610612747, "slug": "los-angeles-lakers", "abbrev": "LAL", "full_name": "Los Angeles Lakers", "city": "Los Angeles", "nickname": "Lakers", "conference": "West", "division": "Pacific", "founded": 1947, "historical_names": ["Minneapolis Lakers"]},
    {"team_id": 1610612763, "slug": "memphis-grizzlies", "abbrev": "MEM", "full_name": "Memphis Grizzlies", "city": "Memphis", "nickname": "Grizzlies", "conference": "West", "division": "Southwest", "founded": 1995, "historical_names": ["Vancouver Grizzlies"]},
    {"team_id": 1610612748, "slug": "miami-heat", "abbrev": "MIA", "full_name": "Miami Heat", "city": "Miami", "nickname": "Heat", "conference": "East", "division": "Southeast", "founded": 1988, "historical_names": []},
    {"team_id": 1610612749, "slug": "milwaukee-bucks", "abbrev": "MIL", "full_name": "Milwaukee Bucks", "city": "Milwaukee", "nickname": "Bucks", "conference": "East", "division": "Central", "founded": 1968, "historical_names": []},
    {"team_id": 1610612750, "slug": "minnesota-timberwolves", "abbrev": "MIN", "full_name": "Minnesota Timberwolves", "city": "Minneapolis", "nickname": "Timberwolves", "conference": "West", "division": "Northwest", "founded": 1989, "historical_names": []},
    {"team_id": 1610612740, "slug": "new-orleans-pelicans", "abbrev": "NOP", "full_name": "New Orleans Pelicans", "city": "New Orleans", "nickname": "Pelicans", "conference": "West", "division": "Southwest", "founded": 2002, "historical_names": ["New Orleans Hornets", "New Orleans/Oklahoma City Hornets"]},
    {"team_id": 1610612752, "slug": "new-york-knicks", "abbrev": "NYK", "full_name": "New York Knicks", "city": "New York", "nickname": "Knicks", "conference": "East", "division": "Atlantic", "founded": 1946, "historical_names": []},
    {"team_id": 1610612760, "slug": "oklahoma-city-thunder", "abbrev": "OKC", "full_name": "Oklahoma City Thunder", "city": "Oklahoma City", "nickname": "Thunder", "conference": "West", "division": "Northwest", "founded": 1967, "historical_names": ["Seattle SuperSonics"]},
    {"team_id": 1610612753, "slug": "orlando-magic", "abbrev": "ORL", "full_name": "Orlando Magic", "city": "Orlando", "nickname": "Magic", "conference": "East", "division": "Southeast", "founded": 1989, "historical_names": []},
    {"team_id": 1610612755, "slug": "philadelphia-76ers", "abbrev": "PHI", "full_name": "Philadelphia 76ers", "city": "Philadelphia", "nickname": "76ers", "conference": "East", "division": "Atlantic", "founded": 1946, "historical_names": ["Syracuse Nationals"]},
    {"team_id": 1610612756, "slug": "phoenix-suns", "abbrev": "PHX", "full_name": "Phoenix Suns", "city": "Phoenix", "nickname": "Suns", "conference": "West", "division": "Pacific", "founded": 1968, "historical_names": []},
    {"team_id": 1610612757, "slug": "portland-trail-blazers", "abbrev": "POR", "full_name": "Portland Trail Blazers", "city": "Portland", "nickname": "Trail Blazers", "conference": "West", "division": "Northwest", "founded": 1970, "historical_names": []},
    {"team_id": 1610612758, "slug": "sacramento-kings", "abbrev": "SAC", "full_name": "Sacramento Kings", "city": "Sacramento", "nickname": "Kings", "conference": "West", "division": "Pacific", "founded": 1923, "historical_names": ["Rochester Royals", "Cincinnati Royals", "Kansas City-Omaha Kings", "Kansas City Kings"]},
    {"team_id": 1610612759, "slug": "san-antonio-spurs", "abbrev": "SAS", "full_name": "San Antonio Spurs", "city": "San Antonio", "nickname": "Spurs", "conference": "West", "division": "Southwest", "founded": 1967, "historical_names": ["Dallas Chaparrals", "Texas Chaparrals"]},
    {"team_id": 1610612761, "slug": "toronto-raptors", "abbrev": "TOR", "full_name": "Toronto Raptors", "city": "Toronto", "nickname": "Raptors", "conference": "East", "division": "Atlantic", "founded": 1995, "historical_names": []},
    {"team_id": 1610612762, "slug": "utah-jazz", "abbrev": "UTA", "full_name": "Utah Jazz", "city": "Salt Lake City", "nickname": "Jazz", "conference": "West", "division": "Northwest", "founded": 1974, "historical_names": ["New Orleans Jazz"]},
    {"team_id": 1610612764, "slug": "washington-wizards", "abbrev": "WAS", "full_name": "Washington Wizards", "city": "Washington", "nickname": "Wizards", "conference": "East", "division": "Southeast", "founded": 1961, "historical_names": ["Chicago Packers", "Chicago Zephyrs", "Baltimore Bullets", "Capital Bullets", "Washington Bullets"]},
]


def download_logos():
    os.makedirs(SVG_DIR, exist_ok=True)
    os.makedirs(PNG_DIR, exist_ok=True)

    for team in TEAMS:
        tid = team["team_id"]
        slug = team["slug"]
        abbrev = team["abbrev"].lower()
        name = team["full_name"]

        # SVG
        svg_url = LOGO_SVG_URL.format(team_id=tid)
        svg_path = os.path.join(SVG_DIR, f"{tid}.svg")
        if not os.path.exists(svg_path):
            resp = safe_get(svg_url, timeout=15)
            if resp and resp.status_code == 200:
                with open(svg_path, "wb") as f:
                    f.write(resp.content)
                log(f"SVG: {name}")
            else:
                log(f"SVG FAILED: {name}")

        # Slug copy
        slug_svg = os.path.join(SVG_DIR, f"{slug}.svg")
        if os.path.exists(svg_path) and not os.path.exists(slug_svg):
            shutil.copy2(svg_path, slug_svg)

        # Abbrev copy
        abbrev_svg = os.path.join(SVG_DIR, f"{abbrev}.svg")
        if os.path.exists(svg_path) and not os.path.exists(abbrev_svg):
            shutil.copy2(svg_path, abbrev_svg)

        # PNG
        png_url = LOGO_PNG_URL.format(team_id=tid)
        png_path = os.path.join(PNG_DIR, f"{tid}.png")
        if not os.path.exists(png_path):
            resp = safe_get(png_url, timeout=15)
            if resp and resp.status_code == 200:
                with open(png_path, "wb") as f:
                    f.write(resp.content)
                log(f"PNG: {name}")
            else:
                log(f"PNG FAILED: {name}")

        # Slug copy
        slug_png = os.path.join(PNG_DIR, f"{slug}.png")
        if os.path.exists(png_path) and not os.path.exists(slug_png):
            shutil.copy2(png_path, slug_png)

    log("All team logos downloaded")


def write_metadata():
    os.makedirs(METADATA_DIR, exist_ok=True)
    out_path = os.path.join(METADATA_DIR, "teams.json")
    with open(out_path, "w") as f:
        json.dump(TEAMS, f, indent=2)
    log(f"Wrote {out_path} ({len(TEAMS)} teams)")


if __name__ == "__main__":
    download_logos()
    write_metadata()

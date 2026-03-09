"""Fetch headshots for historical/retired NBA players."""

import json
import os
import re
import time
import urllib.request

from utils import NBA_HEADERS, STATIC_CDN_HEADERS, log, slugify

ORIGINAL_DIR = os.path.join("players", "headshots", "original")
os.makedirs(ORIGINAL_DIR, exist_ok=True)

HISTORICAL_PLAYERS = [
    (893, "michael-jordan"), (977, "kobe-bryant"), (76003, "kareem-abdul-jabbar"),
    (1495, "tim-duncan"), (2, "magic-johnson"), (76375, "larry-bird"),
    (1718, "shaquille-oneal"), (2037, "allen-iverson"), (165, "charles-barkley"),
    (600005, "julius-erving"), (76786, "wilt-chamberlain"), (77142, "bob-cousy"),
    (78497, "oscar-robertson"), (79, "dominique-wilkins"), (708, "patrick-ewing"),
    (76003, "kareem-abdul-jabbar"), (600001, "bill-russell"), (78049, "jerry-west"),
    (77329, "elgin-baylor"), (76454, "rick-barry"), (255, "reggie-miller"),
    (730, "john-stockton"), (1017, "karl-malone"), (887, "scottie-pippen"),
    (736, "gary-payton"), (951, "alonzo-mourning"), (704, "clyde-drexler"),
    (193, "hakeem-olajuwon"), (78542, "pete-maravich"), (76988, "willis-reed"),
    (1013, "anfernee-hardaway"), (600015, "george-gervin"), (747, "dennis-rodman"),
    (923, "david-robinson"), (76172, "dave-bing"), (76230, "bill-bradley"),
    (1897, "vince-carter"), (169, "mitch-richmond"), (175, "detlef-schrempf"),
    (218, "muggsy-bogues"), (362, "larry-johnson"), (400, "vin-baker"),
    (431, "glen-rice"), (440, "dikembe-mutombo"), (457, "derrick-coleman"),
    (471, "cedric-ceballos"), (490, "nick-van-exel"), (492, "sam-cassell"),
    (502, "alan-houston"), (547, "danny-manning"), (600014, "connie-hawkins"),
    (600018, "artis-gilmore"), (76085, "nate-archibald"), (76118, "paul-arizin"),
    (76584, "dave-cowens"), (76657, "billy-cunningham"), (76721, "bob-dandridge"),
    (76877, "world-b-free"), (77079, "gail-goodrich"), (77163, "hal-greer"),
    (77248, "tom-heinsohn"), (77285, "bailey-howell"), (77349, "dan-issel"),
    (77406, "dennis-johnson"), (77480, "sam-jones"), (77504, "bob-kauffman"),
    (77596, "bob-lanier"), (77672, "clyde-lovellette"), (77696, "jerry-lucas"),
    (77728, "slater-martin"), (77754, "bob-mcadoo"), (77827, "earl-monroe"),
    (78063, "robert-parish"), (78068, "andy-phillip"), (78162, "willis-reed"),
    (78311, "bill-sharman"), (78379, "paul-silas"), (78529, "david-thompson"),
    (78571, "nate-thurmond"), (78654, "wes-unseld"), (78729, "bob-wanzer"),
    (78865, "lenny-wilkens"), (1110, "chris-webber"), (932, "jason-kidd"),
    (934, "grant-hill"), (946, "damon-stoudamire"), (956, "stephon-marbury"),
    (1010, "ray-allen"), (1012, "shareef-abdur-rahim"), (1089, "paul-pierce"),
    (1490, "dirk-nowitzki"), (2005, "carmelo-anthony"), (2406, "dwyane-wade"),
    (2544, "lebron-james"), (2585, "chris-paul"), (101108, "chris-paul"),
    (200746, "dwight-howard"), (201935, "james-harden"), (201939, "stephen-curry"),
]


def fetch_players_from_api():
    """Try to fetch the full historical player list from the NBA Stats API."""
    url = "https://stats.nba.com/stats/playerindex"
    params = "?Historical=1&LeagueID=00&Season=2024-25"
    full_url = url + params
    log(f"Fetching historical player index from {full_url}")
    try:
        req = urllib.request.Request(full_url, headers=NBA_HEADERS)
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        result_set = data["resultSets"][0]
        headers = result_set["headers"]
        rows = result_set["rowSet"]

        ID = headers.index("PERSON_ID")
        FIRST = headers.index("PLAYER_FIRST_NAME")
        LAST = headers.index("PLAYER_LAST_NAME")

        players = []
        for r in rows:
            full_name = f"{r[FIRST]} {r[LAST]}"
            slug = slugify(full_name)
            players.append((r[ID], slug))

        log(f"Got {len(players)} players from NBA Stats API")
        return players
    except Exception as e:
        log(f"NBA Stats API failed: {type(e).__name__}: {e}")
        return None


def download_headshot(nba_id, slug):
    """Download a single headshot from the NBA CDN."""
    out_path = os.path.join(ORIGINAL_DIR, f"{nba_id}-{slug}.png")
    if os.path.exists(out_path):
        return "skip"

    url = f"https://cdn.nba.com/headshots/nba/latest/1040x760/{nba_id}.png"
    try:
        req = urllib.request.Request(url, headers=STATIC_CDN_HEADERS)
        resp = urllib.request.urlopen(req, timeout=10)
        content = resp.read()
        if resp.status == 200 and len(content) > 15000:
            with open(out_path, "wb") as f:
                f.write(content)
            return "ok"
        else:
            return "404"
    except Exception as e:
        return "404"


if __name__ == "__main__":
    # Try NBA Stats API first, fall back to hardcoded list
    players = fetch_players_from_api()
    if players is None:
        log(f"Falling back to hardcoded list of {len(HISTORICAL_PLAYERS)} players")
        players = HISTORICAL_PLAYERS

    downloaded = 0
    skipped = 0
    not_found = 0

    for nba_id, slug in players:
        result = download_headshot(nba_id, slug)
        if result == "ok":
            print(f"OK   {nba_id}-{slug}")
            downloaded += 1
        elif result == "skip":
            print(f"SKIP {nba_id}-{slug}")
            skipped += 1
        else:
            print(f"404  {nba_id}-{slug}")
            not_found += 1

        time.sleep(0.25)

    log(f"Done. Downloaded: {downloaded}, Already existed: {skipped}, 404: {not_found}")

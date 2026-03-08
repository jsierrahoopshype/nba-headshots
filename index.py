"""NBA Headshots & Logos — Python SDK."""

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent


class NBAAssets:
    """Lazy-loading accessor for NBA player headshots and team logos."""

    def __init__(self, root=None):
        self._root = Path(root) if root else _ROOT
        self._players = None
        self._teams = None

    def _load_players(self):
        if self._players is None:
            path = self._root / "players" / "metadata" / "players.json"
            if path.exists():
                with open(path) as f:
                    self._players = json.load(f)
            else:
                self._players = {"players": []}
        return self._players

    def _load_teams(self):
        if self._teams is None:
            path = self._root / "teams" / "metadata" / "teams.json"
            if path.exists():
                with open(path) as f:
                    self._teams = json.load(f)
            else:
                self._teams = []
        return self._teams

    # --- Path helpers ---

    def face_path(self, nba_id):
        """Return Path to 256x256 face crop PNG."""
        return self._root / "players" / "headshots" / "face" / f"{nba_id}.png"

    def thumb_path(self, nba_id):
        """Return Path to 64x64 thumbnail PNG."""
        return self._root / "players" / "headshots" / "thumb" / f"{nba_id}.png"

    def team_logo_path(self, team_id, fmt="svg"):
        """Return Path to team logo (svg or png)."""
        return self._root / "teams" / "logos" / "current" / fmt / f"{team_id}.{fmt}"

    # --- Lookup methods ---

    def player_by_id(self, nba_id):
        """Find player by NBA ID. Returns dict or None."""
        data = self._load_players()
        for p in data["players"]:
            if p["nba_id"] == nba_id:
                return p
        return None

    def player_by_name(self, name):
        """Find player by full name (case-insensitive). Returns dict or None."""
        needle = name.lower()
        data = self._load_players()
        for p in data["players"]:
            if p["full_name"].lower() == needle:
                return p
        return None

    def player_by_slug(self, slug):
        """Find player by slug. Returns dict or None."""
        needle = slug.lower()
        data = self._load_players()
        for p in data["players"]:
            if p["slug"] == needle:
                return p
        return None

    def team_by_slug(self, slug):
        """Find team by slug. Returns dict or None."""
        needle = slug.lower()
        teams = self._load_teams()
        for t in teams:
            if t["slug"] == needle:
                return t
        return None

    def team_by_abbrev(self, abbrev):
        """Find team by abbreviation. Returns dict or None."""
        needle = abbrev.upper()
        teams = self._load_teams()
        for t in teams:
            if t["abbrev"] == needle:
                return t
        return None


# Module-level singleton
assets = NBAAssets()

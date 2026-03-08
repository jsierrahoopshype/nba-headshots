"""NBA Headshots & Logos — Python SDK."""

import json
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent


class NBAAssets:
    """Lazy-loading accessor for NBA player headshots and team logos."""

    def __init__(self, root=None):
        self._root = Path(root) if root else _ROOT
        self._players = None
        self._teams = None
        self._player_by_id = None

    def _load_players(self):
        if self._players is None:
            path = self._root / "players" / "metadata" / "players.json"
            if path.exists():
                with open(path) as f:
                    self._players = json.load(f)
            else:
                self._players = {"players": []}
            self._player_by_id = {p["nba_id"]: p for p in self._players["players"]}
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

    def _filename_for_id(self, nba_id):
        """Get filename from index, or fall back to prefix scan on disk."""
        self._load_players()
        p = self._player_by_id.get(nba_id)
        if p and "headshot" in p and "filename" in p["headshot"]:
            return p["headshot"]["filename"]
        # Fallback: scan directory for file starting with {nba_id}-
        for subdir in ("face", "original", "thumb"):
            d = self._root / "players" / "headshots" / subdir
            if d.exists():
                prefix = f"{nba_id}-"
                for f in os.listdir(d):
                    if f.startswith(prefix) and f.endswith(".png"):
                        return f
        return f"{nba_id}.png"

    # --- Path helpers ---

    def face_path(self, nba_id):
        """Return Path to 256x256 face crop PNG."""
        return self._root / "players" / "headshots" / "face" / self._filename_for_id(nba_id)

    def thumb_path(self, nba_id):
        """Return Path to 64x64 thumbnail PNG."""
        return self._root / "players" / "headshots" / "thumb" / self._filename_for_id(nba_id)

    def team_logo_path(self, team_id, fmt="svg"):
        """Return Path to team logo (svg or png)."""
        return self._root / "teams" / "logos" / "current" / fmt / f"{team_id}.{fmt}"

    # --- Lookup methods ---

    def player_by_id(self, nba_id):
        """Find player by NBA ID. Returns dict or None."""
        self._load_players()
        return self._player_by_id.get(nba_id)

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

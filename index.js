/**
 * NBA Headshots & Logos — JavaScript SDK
 * Works as ESM in browsers and CommonJS in Node.
 */

(function (root, factory) {
  if (typeof module !== "undefined" && module.exports) {
    module.exports = factory();
  } else if (typeof define === "function" && define.amd) {
    define(factory);
  } else {
    root.NBAAssets = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var BASE_URL = "https://jsierrahoopshype.github.io/nba-headshots";
  var _playerIndex = null;
  var _teamIndex = null;
  var _playerPromise = null;
  var _teamPromise = null;
  var _playerByIdMap = null;

  function loadPlayers() {
    if (_playerIndex) return Promise.resolve(_playerIndex);
    if (_playerPromise) return _playerPromise;
    _playerPromise = fetch(BASE_URL + "/players/metadata/players.json")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        _playerIndex = data;
        _playerByIdMap = {};
        data.players.forEach(function (p) {
          _playerByIdMap[p.nba_id] = p;
        });
        return data;
      });
    return _playerPromise;
  }

  function loadTeams() {
    if (_teamIndex) return Promise.resolve(_teamIndex);
    if (_teamPromise) return _teamPromise;
    _teamPromise = fetch(BASE_URL + "/teams/metadata/teams.json")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        _teamIndex = data;
        return data;
      });
    return _teamPromise;
  }

  function filenameForId(nbaId) {
    if (_playerByIdMap && _playerByIdMap[nbaId]) {
      return _playerByIdMap[nbaId].headshot.filename;
    }
    return nbaId + ".png";
  }

  var NBAAssets = {
    /**
     * Override the base URL at runtime.
     */
    setBaseUrl: function (url) {
      BASE_URL = url.replace(/\/+$/, "");
      _playerIndex = null;
      _teamIndex = null;
      _playerPromise = null;
      _teamPromise = null;
      _playerByIdMap = null;
    },

    fallbacks: {
      player: BASE_URL + "/fallbacks/player_silhouette.svg",
      team: BASE_URL + "/fallbacks/player_silhouette.svg",
    },

    // --- Synchronous URL builders (best-effort; call loadPlayers() first for slug filenames) ---

    playerFaceById: function (nbaId) {
      return BASE_URL + "/players/headshots/face/" + filenameForId(nbaId);
    },

    playerThumbById: function (nbaId) {
      return BASE_URL + "/players/headshots/thumb/" + filenameForId(nbaId);
    },

    teamLogoById: function (teamId, format) {
      format = format || "svg";
      return BASE_URL + "/teams/logos/current/" + format + "/" + teamId + "." + format;
    },

    // --- Async lookups (lazy-load index) ---

    playerById: function (nbaId) {
      return loadPlayers().then(function (data) {
        return _playerByIdMap[nbaId] || null;
      });
    },

    playerFaceUrl: function (nbaId) {
      return loadPlayers().then(function () {
        return BASE_URL + "/players/headshots/face/" + filenameForId(nbaId);
      });
    },

    playerThumbUrl: function (nbaId) {
      return loadPlayers().then(function () {
        return BASE_URL + "/players/headshots/thumb/" + filenameForId(nbaId);
      });
    },

    playerByName: function (name) {
      var needle = name.toLowerCase();
      return loadPlayers().then(function (data) {
        var p = data.players.find(function (p) {
          return p.full_name.toLowerCase() === needle;
        });
        return p || null;
      });
    },

    playerBySlug: function (slug) {
      var needle = slug.toLowerCase();
      return loadPlayers().then(function (data) {
        var p = data.players.find(function (p) { return p.slug === needle; });
        return p || null;
      });
    },

    teamBySlug: function (slug) {
      var needle = slug.toLowerCase();
      return loadTeams().then(function (data) {
        var t = data.find(function (t) { return t.slug === needle; });
        return t || null;
      });
    },

    teamByAbbrev: function (abbrev) {
      var needle = abbrev.toUpperCase();
      return loadTeams().then(function (data) {
        var t = data.find(function (t) { return t.abbrev === needle; });
        return t || null;
      });
    },
  };

  return NBAAssets;
});

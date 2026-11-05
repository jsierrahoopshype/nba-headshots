# G League team logos

Official logos for the current NBA G League teams, downloaded once (Nov 5 2026) from the league's
own site: each team's logo as shown on https://gleague.nba.com/teams, served from the league's CDN
(`ak-static.cms.nba.com/wp-content/uploads/logos/nbagleague/{team_id}/primary/L/logo.svg`, the
light-background version).

- `{gleague_team_id}.svg`: the G League team ID used by the league's transaction feed.
- `index.json`: id, name, file and source URL for each logo.

Defunct teams (for example G League Ignite, 1612709930) have no file here; show a neutral text badge.
These are trademarks of their owners. Nothing outside this folder was changed.

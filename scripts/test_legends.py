import urllib.request
import os
players = [
    (893, 'michael-jordan'),
    (977, 'kobe-bryant'),
    (76003, 'kareem-abdul-jabbar'),
    (1495, 'tim-duncan'),
    (2, 'magic-johnson'),
    (76375, 'larry-bird'),
    (1718, 'shaquille-oneal'),
    (2037, 'allen-iverson'),
    (165, 'charles-barkley'),
    (600005, 'julius-erving'),
    (76786, 'wilt-chamberlain'),
    (77142, 'bob-cousy'),
]
for nba_id, slug in players:
    url = f'https://cdn.nba.com/headshots/nba/latest/1040x760/{nba_id}.png'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        content = urllib.request.urlopen(req, timeout=10).read()
        if len(content) > 5000:
            print(f'OK  {nba_id}-{slug} ({len(content)} bytes)')
        else:
            print(f'404 {nba_id}-{slug}')
    except Exception as e:
        print(f'ERR {nba_id}-{slug}: {e}')

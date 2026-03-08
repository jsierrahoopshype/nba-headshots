import urllib.request
import json
import os
import time
os.makedirs('players/headshots/original', exist_ok=True)
os.makedirs('players/metadata', exist_ok=True)
print('Fetching player list...')
req = urllib.request.Request(
    'https://cdn.nba.com/static/json/staticData/playerIndex.json',
    headers={'User-Agent': 'Mozilla/5.0'}
)
data = json.loads(urllib.request.urlopen(req, timeout=15).read())
players = data['players']
print(f'Got {len(players)} players')
missing = []
for i, p in enumerate(players[:10]):
    nba_id = p[2]
    name = f'{p[1]} {p[0]}'
    path = f'players/headshots/original/{nba_id}.png'
    if os.path.exists(path):
        print(f'{i+1}. {name} - cached')
        continue
    try:
        url = f'https://cdn.nba.com/headshots/nba/latest/1040x760/{nba_id}.png'
        req2 = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        content = urllib.request.urlopen(req2, timeout=10).read()
        if len(content) > 5000:
            open(path, 'wb').write(content)
            print(f'{i+1}. {name} - saved ({len(content)} bytes)')
        else:
            print(f'{i+1}. {name} - 404')
            missing.append({'nba_id': nba_id, 'full_name': name})
    except Exception as e:
        print(f'{i+1}. {name} - error: {e}')
    time.sleep(0.25)
print('Done.')

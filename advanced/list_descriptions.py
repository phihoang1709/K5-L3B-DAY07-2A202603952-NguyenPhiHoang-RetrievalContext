"""List figure descriptions grouped by usability for benchmark authoring."""
import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ds = {}
for p in glob.glob(str(HERE / 'data' / 'figure_descriptions*.json')):
    for d in json.loads(Path(p).read_text(encoding='utf-8')):
        ds.setdefault(d['id'], d)
fs = json.loads((HERE / 'data' / 'figures.json').read_text(encoding='utf-8'))

print('=== CHART-like with readable numbers ===')
count = 0
for f in fs:
    d = ds.get(f['id'])
    if d and 'không đọc được' not in d['description'][:250] and len(d['description']) > 150:
        count += 1
        if count <= 16:
            print(f['page'], f['id'][:8], '|', d['description'][:240].replace('\n', ' ~ '))
print('total:', count)
print()
print('=== IMAGE ===')
count = 0
for f in fs:
    d = ds.get(f['id'])
    if d and f['kind'] == 'image' and 'misfit' not in d['description'].lower()[:400]:
        count += 1
        if count <= 10:
            print(f['page'], f['id'][:8], '|', d['description'][:200].replace('\n', ' ~ '))
print('total images:', count)

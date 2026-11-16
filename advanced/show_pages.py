"""Authoring helper: print page text + figure descriptions for given pages."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
pages = {p['page']: p for p in json.loads((HERE / 'data' / 'pages.json').read_text(encoding='utf-8'))}
tables = json.loads((HERE / 'data' / 'tables.json').read_text(encoding='utf-8'))
figures = json.loads((HERE / 'data' / 'figures.json').read_text(encoding='utf-8'))
descs = {}
desc_path = HERE / 'data' / 'figure_descriptions.json'
if desc_path.exists():
    descs = {d['id']: d for d in json.loads(desc_path.read_text(encoding='utf-8'))}

for arg in sys.argv[1:]:
    page = int(arg)
    entry = pages.get(page)
    if not entry:
        print(f'--- page {page}: N/A')
        continue
    print('=' * 30, 'PAGE', page, f"({entry['chars']} chars)")
    print(entry['text'][:2600])
    for t in tables:
        if t['page'] == page:
            print(f'  [TABLE {t["id"][:8]}] rows={t["n_rows"]}:', t['text'][:300])
    for f in figures:
        if f['page'] == page:
            d = descs.get(f['id'])
            crop = f['crop']
            if d:
                print(f'  [FIG {f["id"][:8]} {f["kind"]}] {d["description"][:260]}')
            else:
                print(f'  [FIG {f["id"][:8]} {f["kind"]}] (chưa mô tả) crop={crop}')
    print()

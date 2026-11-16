"""Inspect shard description files: row counts + empty descriptions."""
import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in sorted(glob.glob(str(HERE / 'data' / 'figure_descriptions*.json'))):
    rows = json.loads(Path(p).read_text(encoding='utf-8'))
    empty = [r for r in rows if not r.get('description')]
    print(Path(p).name, len(rows), 'rows,', len(empty), 'empty')
    for row in empty[:5]:
        print('   empty:', row['id'][:8], row.get('crop'))
total = sum(len(json.loads(Path(p).read_text(encoding='utf-8')))
            for p in glob.glob(str(HERE / 'data' / 'figure_descriptions*.json')))
print('TOTAL', total)

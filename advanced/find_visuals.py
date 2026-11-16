"""Find genuine charts (axes/years/trends) and informative event photos."""
import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ds = {}
for p in glob.glob(str(HERE / 'data' / 'figure_descriptions*.json')):
    for d in json.loads(Path(p).read_text(encoding='utf-8')):
        ds.setdefault(d['id'], d)
fs = json.loads((HERE / 'data' / 'figures.json').read_text(encoding='utf-8'))

print('=== desc says BIỂU ĐỒ ===')
for f in fs:
    d = ds.get(f['id'])
    if d and 'biểu đồ' in d['description'].lower()[:30]:
        print(f['page'], f['id'][:8], '|', d['description'][:280].replace('\n', ' ~ '))
print()
print('=== desc mentions sự kiện / ký kết / khai trương / lễ / trao tặng (event photos) ===')
for f in fs:
    d = ds.get(f['id'])
    if not d:
        continue
    low = d['description'].lower()
    if any(k in low for k in ('ký kết', 'khai trương', 'lễ ', 'trao tặng', 'hợp tác', 'sự kiện', 'tổng giám đốc', 'chủ tịch')):
        print(f['page'], f['id'][:8], f['kind'], '|', d['description'][:220].replace('\n', ' ~ '))

"""Compare agent traces of two runs on selected question ids (diagnostic)."""
import json
import sys
from pathlib import Path

base = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
other = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
qmap = {q['id']: q for q in json.loads(Path(sys.argv[3]).read_text(encoding='utf-8'))}
ids = sys.argv[4].split(',') if len(sys.argv) > 4 else list(qmap)

for qid in ids:
    q = qmap[qid]
    ta = next(t for t in base if t['query_id'] == qid)
    tb = next(t for t in other if t['query_id'] == qid)
    print('=' * 30, qid, '| gold_answer:', json.dumps(q.get('expected_answer'), ensure_ascii=False))
    print('  [A]', ta['status'], 'searches=%d' % ta['searches'], '::',
          json.dumps(ta['answer'], ensure_ascii=False)[:300])
    print('      cites:', ta['citations'])
    print('  [B]', tb['status'], 'searches=%d' % tb['searches'], '::',
          json.dumps(tb['answer'], ensure_ascii=False)[:300])
    print('      cites:', tb['citations'])
    print()

"""Print a human grading sheet from an agent run: answer vs gold + cited chunks."""
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
questions = {q['id']: q for q in json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))}
chunks = {c['id']: c for c in json.loads(Path(sys.argv[3]).read_text(encoding='utf-8'))}
traces = json.loads((run_dir / 'traces.json').read_text(encoding='utf-8'))

for t in traces:
    q = questions[t['query_id']]
    answerable = q.get('answerable') is not False
    print('=' * 34, t['query_id'], '(answerable)' if answerable else '(NO-EVIDENCE)')
    print('Q:', q['question'])
    if answerable:
        print('GOLD ANSWER:', q.get('expected_answer'))
        print('GOLD LOCUS:', [(g['source_id'], g['page']) for g in q.get('gold', [])])
    else:
        print('ABSENCE REASON:', q.get('absence_reason'))
    print('AGENT [%s] %d searches:' % (t['status'], t['searches']))
    print('   ', json.dumps(t['answer'], ensure_ascii=False))
    for cid in t['citations']:
        c = chunks.get(cid)
        locus = f"page {c['page']}" if c else 'NOT IN CORPUS'
        print('    cite', cid, '->', locus)
        if c:
            print('       text:', json.dumps(c['text'], ensure_ascii=False)[:400])
    print()

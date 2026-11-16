"""Read-only trace inspector for label audit: evidence-relative facts only.

Usage:
  python inspect_trace.py <traces.json> <questions.json> <chunks.json> <ids>
    ids: comma-separated query ids | 'ALL:answerable' | 'text=<substring>'
Prints, per query: status/answer/citations, per-event queries and context ids,
gold-locating chunk ids, whether cited chunk / final context contains the gold
evidence, and (for no-evidence ids) absence-keyword presence per cited chunk.
Never writes anything.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline import hit  # noqa: E402

traces_path, questions_path, chunks_path = (Path(p) for p in sys.argv[1:4])
ids_arg = sys.argv[4]
chunks = json.loads(chunks_path.read_text(encoding='utf-8'))
by_id = {c['id']: c for c in chunks}

if ids_arg.startswith('text='):
    needle = ids_arg[5:].casefold()
    for c in chunks:
        if needle in c['text'].casefold():
            print(c['id'], '| page', c['page'], '| chapter', c['metadata'].get('chapter'),
                  '|', repr(c['text'][:150]))
    sys.exit(0)

traces = json.loads(traces_path.read_text(encoding='utf-8'))
questions = {q['id']: q for q in json.loads(questions_path.read_text(encoding='utf-8'))}


def gold_chunk_ids(q):
    return [c['id'] for c in chunks if hit(c, q['gold'])]


if ids_arg == 'ALL:answerable':
    ids = [t['query_id'] for t in traces if questions[t['query_id']].get('answerable') is not False]
else:
    ids = ids_arg.split(',')

for qid in ids:
    q = questions[qid]
    t = next(t for t in traces if t['query_id'] == qid)
    answerable = q.get('answerable') is not False
    print('=' * 40, qid, '| answerable:', answerable)
    print('Q:', q['question'])
    if answerable:
        print('EXPECTED:', q.get('expected_answer'))
        gids = gold_chunk_ids(q)
        print('GOLD EVIDENCE IN CHUNKS:', gids, '(page', q['gold'][0]['page'], ')')
    else:
        print('ABSENCE:', q.get('absence_reason'))
    if 'status' in t:  # agent trace
        print('AGENT:', t['status'], '| searches:', t.get('searches'))
        print('ANSWER:', json.dumps(t.get('answer'), ensure_ascii=False))
        print('CITATIONS:', t.get('citations'))
        final_ctx = []
        for e in t.get('events', []):
            if e.get('event') == 'search':
                final_ctx = e.get('context_ids') or []
                print('  search query:', json.dumps(e.get('query')), '-> ctx:', final_ctx)
            elif e.get('event') != 'answer':
                print('  event:', e.get('event'))
        print('FINAL CONTEXT:', final_ctx)
    else:  # retrieval trace
        final_ctx = t.get('context_ids') or []
        print('RANKED:', [r['id'] for r in t.get('results', [])])
        print('CONTEXT IDS:', final_ctx)
    if answerable:
        for cid in t.get('citations', []):
            c = by_id.get(cid)
            if c is None:
                print('  cite', cid, '-> NOT IN CORPUS')
                continue
            has_gold = hit(c, q['gold'])
            print('  cite', cid, '-> page', c['page'], '| contains gold evidence:', has_gold)
        in_ctx = [cid for cid in final_ctx if cid in gids]
        print('  GOLD CHUNKS IN FINAL CONTEXT:', in_ctx or 'NONE')
    else:
        for cid in t.get('citations', []):
            c = by_id.get(cid)
            text = json.dumps(c['text'], ensure_ascii=False) if c else 'NOT IN CORPUS'
            print('  cite', cid, '->', text[:220])
    print()

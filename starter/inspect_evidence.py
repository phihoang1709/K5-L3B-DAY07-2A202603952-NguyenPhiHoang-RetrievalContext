"""One-off diagnostic: list answerable questions whose Day 6 evidence quote
is not a verbatim substring of any exported chunk (hyphenation/line breaks)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline import hit

REPO = Path(__file__).resolve().parents[1]
questions = json.loads((REPO / 'data' / 'questions.json').read_text(encoding='utf-8')) \
    if (REPO / 'data' / 'questions.json').exists() else []
if not questions:
    day6 = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    from convert_day6 import convert_question
    questions = [convert_question(q) for q in day6['questions']]
chunks = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))

for q in questions:
    if q.get('answerable') is False:
        continue
    ok = any(hit(c, q['gold']) for c in chunks)
    if not ok:
        g = q['gold'][0]
        page_chunks = [c for c in chunks if c['page'] == g['page']]
        print(f"--- {q['id']} (page {g['page']}) MISSING evidence:")
        print('   quote:', repr(g['evidence'][:100]))
        for c in page_chunks[:4]:
            print('   chunk', c['id'], repr(c['text'][:200]))

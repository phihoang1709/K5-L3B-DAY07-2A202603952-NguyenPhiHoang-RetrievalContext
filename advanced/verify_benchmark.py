"""Verify the advanced benchmark: gold containment, locus existence, absence.

Checks per question (schema in benchmark_questions.json):
- answerable: every text gold entry's evidence is a verbatim substring of a
  chunk on the gold page; every figure gold entry resolves to a described
  figure on the gold page whose crop file exists; expected_answer non-empty.
- no_evidence: every absence_keyword is absent from ALL chunk text.
- counts: dev >= 15 answerable + 3 no_evidence; test >= 24 answerable + 6
  no_evidence; group minimums for test (bang>=6, anh>=5, bieu_do>=5,
  multi_hop>=4, text>=4); ids unique; split valid.

Usage:
  python verify_benchmark.py                    # verify benchmark_questions.json
  python verify_benchmark.py --search "ATM"     # keyword search helper (authoring)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / 'data'
CROPS_DIR = HERE / 'crops'
BENCH_PATH = HERE / 'benchmark_questions.json'

GROUP_MIN_TEST = {'bang': 6, 'anh': 5, 'bieu_do': 5, 'multi_hop': 4, 'text': 4}
MIN = {'dev': (15, 3), 'test': (24, 6)}


def load_pages_chunks() -> dict[int, list[str]]:
    pages = json.loads((DATA_DIR / 'pages.json').read_text(encoding='utf-8'))
    tables = json.loads((DATA_DIR / 'tables.json').read_text(encoding='utf-8'))
    chunks: dict[int, list[str]] = {}
    for page in pages:
        chunks.setdefault(page['page'], []).append(page['text'])
    for table in tables:
        chunks.setdefault(table['page'], []).append(table['text'])
    return chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--search', default=None, help='tìm keyword trong toàn bộ text (authoring)')
    parser.add_argument('--path', type=Path, default=BENCH_PATH)
    args = parser.parse_args()
    chunks = load_pages_chunks()
    all_text = '\n'.join('\n'.join(v) for v in chunks.values())
    if args.search:
        needle = args.search.casefold()
        for page, texts in sorted(chunks.items()):
            joined = '\n'.join(texts).casefold()
            if needle in joined:
                position = joined.index(needle)
                print(page, ':', repr(joined[max(0, position - 60):position + 80]))
        return

    questions = json.loads(args.path.read_text(encoding='utf-8'))
    figures = json.loads((DATA_DIR / 'figures.json').read_text(encoding='utf-8'))
    fig_index = {(f['page'], f['id']): f for f in figures}
    errors = []
    counts: dict[tuple[str, str], int] = {}
    ids = [q['id'] for q in questions]
    if len(set(ids)) != len(ids):
        errors.append('ID trùng')
    for q in questions:
        split, group = q.get('split'), q.get('group')
        if split not in ('dev', 'test') or group not in ('bang', 'anh', 'bieu_do', 'multi_hop', 'text', 'no_evidence'):
            errors.append(f"{q['id']}: split/group không hợp lệ ({split}/{group})")
            continue
        counts[(split, group)] = counts.get((split, group), 0) + 1
        if split == 'test' and group != 'no_evidence' and group in GROUP_MIN_TEST:
            pass
        if q.get('answerable') is False or group == 'no_evidence':
            for keyword in q.get('absence_keywords', []):
                if keyword.casefold() in all_text.casefold():
                    errors.append(f"{q['id']}: absence keyword {keyword!r} CÓ trong corpus")
            if not q.get('absence_reason'):
                errors.append(f"{q['id']}: thiếu absence_reason")
            continue
        if not str(q.get('expected_answer', '')).strip():
            errors.append(f"{q['id']}: thiếu expected_answer")
        for gold in q.get('gold', []):
            page, evidence = gold.get('page'), gold.get('evidence')
            if evidence and page in chunks:
                if evidence not in '\n'.join(chunks[page]):
                    errors.append(f"{q['id']}: evidence không nằm trọn trong trang {page}: {evidence[:60]!r}")
            elif evidence:
                errors.append(f"{q['id']}: gold page {page} không tồn tại")
        for ref in q.get('gold_figures', []):
            figure = fig_index.get((ref.get('page'), ref.get('figure_id')))
            if figure is None:
                errors.append(f"{q['id']}: gold_figure {ref.get('figure_id')} không tồn tại ở trang {ref.get('page')}")
            elif not (CROPS_DIR / figure['crop']).exists():
                errors.append(f"{q['id']}: crop thiếu {figure['crop']}")
        if group == 'multi_hop' and len(q.get('gold', [])) + len(q.get('gold_figures', [])) < 2:
            errors.append(f"{q['id']}: multi_hop cần >= 2 gold loci")
    for split, (answerable_min, noev_min) in MIN.items():
        have_answerable = sum(v for (s, g), v in counts.items() if s == split and g != 'no_evidence')
        have_noev = counts.get((split, 'no_evidence'), 0)
        if have_answerable < answerable_min:
            errors.append(f'{split}: chỉ có {have_answerable} câu có đáp án (< {answerable_min})')
        if have_noev < noev_min:
            errors.append(f'{split}: chỉ có {have_noev} câu no_evidence (< {noev_min})')
    for group, minimum in GROUP_MIN_TEST.items():
        have = counts.get(('test', group), 0)
        if have < minimum:
            errors.append(f'test/{group}: {have} < {minimum}')
    if errors:
        print('VERIFY FAIL:')
        for error in errors:
            print(' -', error)
        sys.exit(1)
    print(json.dumps({'verify': 'PASS', 'counts': {f'{s}/{g}': v for (s, g), v in sorted(counts.items())},
                      'total': len(questions)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Benchmark retrieval methods on one split with identical questions/corpus.

Methods: tfidf (starter.baseline, offline), dense (Day 6 pgvector store),
hybrid_rrf (fusion). Metrics per BENCHMARK.md section 2, computed only over
answerable questions (no-evidence questions are excluded from retrieval
denominators; their traces are still recorded with metrics null):
- Hit@1 / Evidence Hit@3: gold evidence inside top-1 / top-3 chunks
  (same hit() rule as the TF-IDF baseline);
- Context Evidence Rate: gold evidence inside the final packed context
  (budget chars, pack_context from baseline.py).

Gold is read only AFTER search, to mark hits; it never enters any query or
filter. Filters come from the question's user-provided `filter` field.
"""
import argparse
import json
import statistics
import time
from pathlib import Path

from baseline import TfidfIndex, hit, pack_context


def load_questions(path: Path, split: str) -> list[dict]:
    questions = json.loads(path.read_text(encoding='utf-8'))
    selected = [q for q in questions if q.get('split') == split]
    if not selected:
        raise ValueError(f'không có câu hỏi thuộc split {split!r}')
    return selected


def run_method(name: str, index, questions: list[dict], *, top_k: int, budget: int) -> dict:
    traces = []
    # dense leg lives at index.dense for hybrid, at index itself for dense
    dense_leg = getattr(index, 'dense', index)
    embedding_inputs_before = getattr(dense_leg, 'calls', 0)
    for q in questions:
        answerable = q.get('answerable') is not False
        filters = q.get('filter')
        started = time.perf_counter()
        results = index.search(q['question'], filters=filters, top_k=top_k)
        elapsed_ms = (time.perf_counter() - started) * 1000
        context, ids = pack_context(results, budget=budget)
        marked = [{**c, 'hit': hit(c, q['gold'])} for c in results] if answerable else results
        # BENCHMARK.md: Hit@1 / Evidence Hit@3 use a fixed top-3 cutoff even
        # when the pipeline itself retrieves deeper than 3.
        top3 = marked[:3] if answerable else []
        traces.append({
            'query_id': q['id'], 'split': q['split'], 'question': q['question'],
            'answerable': answerable, 'filter': filters,
            'strategy': name, 'top_k': top_k, 'budget_chars': budget,
            'results': marked, 'context': context, 'context_ids': ids,
            'context_chars': len(context), 'elapsed_ms': elapsed_ms,
            'hit1': (bool(marked and marked[0]['hit']) if answerable else None),
            'hit3': (any(c['hit'] for c in top3) if answerable else None),
            'context_hit': (any(c['hit'] and c['id'] in ids for c in marked) if answerable else None),
        })
    answerable_traces = [t for t in traces if t['answerable']]
    dense = dense_leg if isinstance(getattr(dense_leg, 'calls', None), int) else None
    summary = {
        'strategy': name, 'split': questions[0]['split'], 'n_questions': len(traces),
        'n_answerable': len(answerable_traces),
        'hit1': sum(t['hit1'] for t in answerable_traces),
        'hit3': sum(t['hit3'] for t in answerable_traces),
        'context_hit': sum(t['context_hit'] for t in answerable_traces),
        'hit1_rate': (sum(t['hit1'] for t in answerable_traces) / len(answerable_traces)
                      if answerable_traces else None),
        'hit3_rate': (sum(t['hit3'] for t in answerable_traces) / len(answerable_traces)
                      if answerable_traces else None),
        'context_hit_rate': (sum(t['context_hit'] for t in answerable_traces) / len(answerable_traces)
                             if answerable_traces else None),
        'avg_context_chars': (statistics.mean(t['context_chars'] for t in answerable_traces)
                              if answerable_traces else None),
        'median_ms': (statistics.median(t['elapsed_ms'] for t in answerable_traces)
                      if answerable_traces else None),
        'embedding_inputs': ((dense.calls - embedding_inputs_before) if dense else 0),
    }
    return {'summary': summary, 'traces': traces}


def build_index(name: str, chunks: list[dict]):
    if name == 'tfidf':
        class TfidfRetriever:
            def __init__(self, chunks): self.index = TfidfIndex(chunks)
            def search(self, query, *, filters, top_k):
                if filters:  # lexical baseline has no store filter; skip would
                    raise ValueError('tfidf baseline không hỗ trợ filter')
                return self.index.search(query, top_k=top_k)
        return TfidfRetriever(chunks)
    if name == 'dense':
        from dense_retriever import DenseRetriever
        return DenseRetriever()
    if name == 'hybrid':
        from dense_retriever import DenseRetriever
        from hybrid_retrieval import HybridRRF
        return HybridRRF(chunks, DenseRetriever())
    raise ValueError(f'phương pháp chưa hỗ trợ: {name}')


def main():
    parser = argparse.ArgumentParser(description='So sánh các phương pháp retrieval trên một split')
    parser.add_argument('--chunks', required=True, type=Path)
    parser.add_argument('--questions', required=True, type=Path)
    parser.add_argument('--split', required=True, choices=('dev', 'test'))
    parser.add_argument('--methods', nargs='+', default=['tfidf', 'dense', 'hybrid'])
    parser.add_argument('--top-k', type=int, default=3)
    parser.add_argument('--budget', type=int, default=800)
    parser.add_argument('--output', required=True, type=Path, help='thư mục kết quả')
    args = parser.parse_args()
    chunks = json.loads(args.chunks.read_text(encoding='utf-8'))
    questions = load_questions(args.questions, args.split)
    args.output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for name in args.methods:
        if name == 'tfidf':
            # Same questions as the other methods for a fair denominator; the
            # lexical baseline ignores chapter filters (documented per method).
            tfidf_questions = [{**q, 'filter': None} for q in questions]
            run = run_method(name, build_index(name, chunks), tfidf_questions,
                             top_k=args.top_k, budget=args.budget)
            run['summary']['note'] = 'tfidf chạy trên toàn bộ câu hỏi, không dùng filter'
        else:
            run = run_method(name, build_index(name, chunks), questions,
                             top_k=args.top_k, budget=args.budget)
        folder = args.output / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'traces.json').write_text(
            json.dumps(run['traces'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (folder / 'summary.json').write_text(
            json.dumps(run['summary'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        summaries.append(run['summary'])
        print(json.dumps(run['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()

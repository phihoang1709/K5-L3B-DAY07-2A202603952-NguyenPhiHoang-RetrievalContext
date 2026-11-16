"""Run the real agent (OpenRouter controller + Day 6 retriever) on a split.

For every question: fresh controller, run_agent() with the configured
retriever/top-k/budget/max-searches. Gold NEVER enters the agent: only id,
split, question text and the question's user-provided filter are read here.
Per-question exceptions are recorded as status='error' traces (never faked);
transient transport errors get one retry after a short backoff.

Outputs (under --output):
- traces.json   per agent_metrics contract: query_id/status/events/citations
                (+ answer, timings, searches, per-question usage)
- cases.json    [{id, split, answerable}] for agent_metrics
- review_template.json  human-grading worksheet: expected answer only here
- run_summary.json       config + status/usage totals
"""
import argparse
import json
import time
from pathlib import Path

from agentic import run_agent
from openrouter_controller import OpenRouterController


def build_retriever(kind: str, chunks_path: Path | None):
    if kind == 'dense':
        from dense_retriever import DenseRetriever
        return DenseRetriever()
    if kind == 'hybrid':
        from hybrid_retrieval import HybridRRF
        from dense_retriever import DenseRetriever
        if chunks_path is None:
            raise ValueError('--chunks bắt buộc khi --retriever hybrid')
        chunks = json.loads(chunks_path.read_text(encoding='utf-8'))
        return HybridRRF(chunks, DenseRetriever())
    raise ValueError(f'retriever chưa hỗ trợ: {kind}')


def run_one(question: dict, retriever, *, model: str, max_searches: int,
            top_k: int, budget: int, retries: int) -> dict:
    """Run one question; retry transport errors once-ish; record everything."""
    started = time.perf_counter()
    controller = OpenRouterController(model=model)
    filters = question.get('filter')
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        try:
            result = run_agent(question['question'], controller, retriever,
                               filters=filters, max_searches=max_searches,
                               top_k=top_k, budget=budget)
            trace = {'query_id': question['id'], 'split': question['split'],
                     'status': result['status'], 'answer': result['answer'],
                     'citations': result['citations'], 'events': result['events'],
                     'searches': sum(1 for e in result['events'] if e.get('event') == 'search'),
                     'elapsed_ms': round((time.perf_counter() - started) * 1000, 1),
                     'model': controller.model, 'usage': dict(controller.usage_totals)}
            return trace
        except (RuntimeError, ConnectionError) as exc:
            if attempt == attempts:
                return {'query_id': question['id'], 'split': question['split'],
                        'status': 'error', 'answer': None, 'citations': [], 'events': [],
                        'searches': 0, 'elapsed_ms': round((time.perf_counter() - started) * 1000, 1),
                        'model': controller.model, 'usage': dict(controller.usage_totals),
                        'error': str(exc)[:300]}
            time.sleep(3)


def main():
    parser = argparse.ArgumentParser(description='Chạy agent thật trên một split benchmark')
    parser.add_argument('--questions', required=True, type=Path)
    parser.add_argument('--split', required=True, choices=('dev', 'test'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--retriever', default='dense', choices=('dense', 'hybrid'))
    parser.add_argument('--chunks', type=Path, default=None, help='chunks.json (bắt buộc nếu hybrid)')
    parser.add_argument('--top-k', type=int, default=3)
    parser.add_argument('--budget', type=int, default=800)
    parser.add_argument('--max-searches', type=int, default=4)
    parser.add_argument('--model', default=None, help='override OPENROUTER_MODEL')
    parser.add_argument('--limit', type=int, default=None, help='chỉ chạy N câu đầu (smoke)')
    parser.add_argument('--retries', type=int, default=1)
    args = parser.parse_args()

    questions = [q for q in json.loads(args.questions.read_text(encoding='utf-8'))
                 if q.get('split') == args.split]
    if not questions:
        raise ValueError(f'không có câu hỏi split {args.split}')
    if args.limit:
        questions = questions[:args.limit]
    retriever = build_retriever(args.retriever, args.chunks)

    traces = []
    for i, question in enumerate(questions, 1):
        trace = run_one(question, retriever, model=args.model, max_searches=args.max_searches,
                        top_k=args.top_k, budget=args.budget, retries=args.retries)
        traces.append(trace)
        print(f"[{i}/{len(questions)}] {trace['query_id']}: {trace['status']}"
              f" ({trace['searches']} searches, {trace['elapsed_ms']}ms)")
        time.sleep(0.5)

    cases = [{'id': q['id'], 'split': q['split'], 'answerable': q.get('answerable') is not False}
             for q in questions]
    q_by_id = {q['id']: q for q in questions}
    t_by_id = {t['query_id']: t for t in traces}
    review_template = []
    for q in questions:
        trace = t_by_id[q['id']]
        final_context_ids = next((e.get('context_ids') for e in reversed(trace['events'])
                                  if e.get('event') == 'search'), [])
        row = {'query_id': q['id'], 'question': q['question'],
               'answerable': q.get('answerable') is not False,
               'expected_answer': q.get('expected_answer'),
               'agent_status': trace['status'], 'agent_answer': trace['answer'],
               'agent_citations': trace['citations'], 'final_context_ids': final_context_ids,
               'citation_support': [None] * len(trace['citations']),
               'notes': ''}
        if row['answerable']:
            row['answer_grade'] = None
        else:
            row['abstention_correct'] = None
        review_template.append(row)

    usage_totals = {'prompt_tokens': 0, 'completion_tokens': 0, 'calls': 0}
    for t in traces:
        for key in usage_totals:
            usage_totals[key] += (t.get('usage') or {}).get(key, 0)
    statuses = {}
    for t in traces:
        statuses[t['status']] = statuses.get(t['status'], 0) + 1
    run_summary = {
        'split': args.split, 'retriever': args.retriever, 'top_k': args.top_k,
        'budget': args.budget, 'max_searches': args.max_searches,
        'model': traces[0].get('model') if traces else None,
        'n': len(traces), 'statuses': statuses, 'usage_totals': usage_totals,
        'embedding_inputs': getattr(retriever, 'calls', getattr(getattr(retriever, 'dense', None), 'calls', 0)),
        'total_elapsed_ms': round(sum(t['elapsed_ms'] for t in traces), 1),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    for name, obj in (('traces.json', traces), ('cases.json', cases),
                      ('review_template.json', review_template), ('run_summary.json', run_summary)):
        (args.output / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n',
                                        encoding='utf-8')
    print(json.dumps(run_summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

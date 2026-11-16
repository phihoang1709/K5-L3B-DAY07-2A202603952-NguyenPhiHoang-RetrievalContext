"""Dense retrieval on the Day 6 vector store (strategy C, qwen3-embedding-8b).

Implements the Retriever protocol from agentic.py: embed the query with the
SAME Day 6 embedding model (dimensions must match the index), search pgvector
by cosine, and return Day 7-schema chunks (id/text/source_id/source/page/
metadata/score). Filters pass through Day 6's allowlist (chapter, page, ...).
"""
from __future__ import annotations

import time
from typing import Any

from day6_bridge import STRATEGY, MyEmbedder, PgVectorStore
from day7_env import load_env, require

# transient-transport retry (same request, no fallback); backoff between tries
TRANSPORT_RETRIES = 3
BACKOFF_SECONDS = (5, 15, 30)


class DenseRetriever:
    """Query-embedding adapter over the real Day 6 pgvector index."""

    def __init__(self, strategy: str = STRATEGY, *, tables_prefix: str = 'day6_') -> None:
        load_env()
        self.strategy = strategy
        self.embedder = MyEmbedder()          # model/dim from EMBEDDING_MODEL env
        self.store = PgVectorStore(require('DATABASE_URL'), tables_prefix=tables_prefix)
        meta = self.store.get_strategy_meta(strategy)
        if meta is None:
            raise RuntimeError(f'strategy {strategy!r} chưa được index; chạy ingest Day 6')
        self.model_name = self.embedder.model_name
        self.dimensions = meta['dimensions']
        self.calls = 0
        self.errors = 0
        self.elapsed_ms: list[float] = []

    def search(self, query: str, *, filters: dict[str, Any] | None, top_k: int) -> list[dict[str, Any]]:
        """Embed + cosine search; retry transient transport errors, else raise.

        Retries re-issue the SAME request with backoff; a final failure still
        propagates (no mock fallback). Provider HTTP errors (e.g. 401) raise
        immediately on the first attempt.
        """
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(TRANSPORT_RETRIES):
            try:
                vector = self.embedder.embed_query(query)
                rows = self.store.search(self.strategy, vector, top_k=top_k, filters=filters,
                                         model_identity={
                                             'model_name': self.model_name,
                                             'served_model': getattr(self.embedder, 'served_model', None)})
                last_error = None
                break
            except RuntimeError as exc:
                message = str(exc)
                if 'HTTP' in message or attempt == TRANSPORT_RETRIES - 1:
                    raise
                last_error = exc
                time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
        if last_error is not None:
            raise last_error
        self.elapsed_ms.append((time.perf_counter() - started) * 1000)
        self.calls += 1
        results = [{'id': r['chunk_id'], 'text': r['text'], 'source_id': r['document_id'],
                    'source': r['source'], 'page': r['page'], 'metadata': r['metadata'],
                    'score': r['score'], 'strategy': 'dense'}
                   for r in rows]
        if len(results) > top_k or len({r['id'] for r in results}) != len(results):
            raise ValueError('dense retriever trả quá top_k hoặc ID trùng')
        return results


def main():
    """Smoke check: one query through the real store, printing top hits."""
    import argparse
    import json
    parser = argparse.ArgumentParser(description='Smoke test dense retrieval trên store Day 6')
    parser.add_argument('--query', default='Trong Python, biến (variable) được định nghĩa là gì?')
    parser.add_argument('--top-k', type=int, default=3)
    args = parser.parse_args()
    retriever = DenseRetriever()
    results = retriever.search(args.query, filters=None, top_k=args.top_k)
    for rank, r in enumerate(results, 1):
        print(json.dumps({'rank': rank, 'id': r['id'], 'page': r['page'],
                          'score': round(r['score'], 4), 'text': r['text'][:120]},
                         ensure_ascii=False))
    print(f'embedding model: {retriever.model_name} ({retriever.dimensions}d)')


if __name__ == '__main__':
    main()

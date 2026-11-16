"""Hybrid retrieval: Reciprocal Rank Fusion of dense (Day 6 store) + TF-IDF.

A distinct ranking method per GUIDE.md: dense cosine candidates and lexical
TF-IDF candidates are fused with RRF, score(d) = sum over methods of
1 / (k + rank), k = 60 (standard RRF constant). Filters are user-provided
question metadata only: the dense leg enforces them in pgvector (Day 6
allowlist) and the TF-IDF leg post-filters on chunk metadata; never gold.
"""
from __future__ import annotations

import time
from typing import Any

from baseline import TfidfIndex
from dense_retriever import DenseRetriever

RRF_K = 60


class HybridRRF:
    """Fuse dense + lexical rankings; same Retriever interface as agentic.py."""

    def __init__(self, chunks: list[dict], dense: DenseRetriever, *,
                 candidate_pool: int = 10, rrf_k: int = RRF_K) -> None:
        self.dense = dense
        self.lexical = TfidfIndex(chunks)
        self.chunks_by_id = {c['id']: c for c in chunks}
        self.candidate_pool = candidate_pool
        self.rrf_k = rrf_k
        self.strategy = 'hybrid_rrf'

    def _lexical_candidates(self, query: str, filters: dict[str, Any] | None, pool: int) -> list[dict]:
        results = self.lexical.search(query, top_k=pool)
        if not filters:
            return results
        keep = []
        for r in results:
            meta = r.get('metadata') or {}
            if all(meta.get(key) == value for key, value in filters.items()):
                keep.append(r)
        return keep

    def search(self, query: str, *, filters: dict[str, Any] | None, top_k: int) -> list[dict[str, Any]]:
        started = time.perf_counter()
        dense_hits = self.dense.search(query, filters=filters, top_k=self.candidate_pool)
        lexical_hits = self._lexical_candidates(query, filters, self.candidate_pool)
        scores: dict[str, float] = {}
        for ranking in (dense_hits, lexical_hits):
            for rank, chunk in enumerate(ranking, start=1):
                scores[chunk['id']] = scores.get(chunk['id'], 0.0) + 1.0 / (self.rrf_k + rank)
        fused = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
        results = []
        for chunk_id, rrf_score in fused:
            base = next((c for c in dense_hits if c['id'] == chunk_id), None)
            if base is None:
                base = {**self.chunks_by_id[chunk_id], 'score': 0.0, 'strategy': 'tfidf'}
            results.append({**base, 'score': rrf_score, 'strategy': self.strategy,
                            'rrf_k': self.rrf_k})
        self.last_elapsed_ms = (time.perf_counter() - started) * 1000
        if len(results) > top_k or len({r['id'] for r in results}) != len(results):
            raise ValueError('hybrid retriever trả quá top_k hoặc ID trùng')
        return results

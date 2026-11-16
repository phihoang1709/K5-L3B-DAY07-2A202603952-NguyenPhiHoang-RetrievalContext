"""Bridge to the Day 6 repo: reuse its PgVectorStore and OpenRouter embedder.

Day 7's assignment is to CONNECT the Day 6 embedding + vector store, so we
import the Day 6 adapters instead of duplicating them: store.py (PostgreSQL +
pgvector, parameterized allowlisted filters) and embeddings.py (OpenRouter
embeddings, stdlib urllib). Location resolution order: $DAY6_REPO, then a
sibling K5-L3B-DAY06* directory next to this repo.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_THIS_REPO_ROOT = Path(__file__).resolve().parents[1]


def find_day6_repo() -> Path:
    """Return the Day 6 repo root; raise with instructions when not found."""
    env_path = os.environ.get('DAY6_REPO', '').strip()
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(sorted((_THIS_REPO_ROOT.parent).glob('K5-L3B-DAY06*')))
    for candidate in candidates:
        if (candidate / 'starter' / 'src' / 'store.py').is_file():
            return candidate
    raise FileNotFoundError(
        'không tìm thấy repo Day 6: đặt biến môi trường DAY6_REPO trỏ tới thư mục'
        ' repo Day 6 (chứa starter/src/store.py)')


def import_day6_modules() -> dict:
    """Import Day 6 src.store + src.embeddings (and src.models for types).

    Adds <day6>/starter to sys.path once; returns the loaded modules.
    """
    repo = find_day6_repo()
    starter_dir = repo / 'starter'
    if str(starter_dir) not in sys.path:
        sys.path.insert(0, str(starter_dir))
    import src.embeddings  # noqa: E402
    import src.models  # noqa: E402
    import src.store  # noqa: E402
    return {'repo': repo, 'embeddings': src.embeddings,
            'models': src.models, 'store': src.store}


DAY6 = import_day6_modules()
PgVectorStore = DAY6['store'].PgVectorStore
MyEmbedder = DAY6['embeddings'].MyEmbedder

STRATEGY = 'C'  # Day 6 conclusion: paragraph chunks + chapter filter enforcement

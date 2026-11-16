"""Shared Day 7 environment loading: .env at repo root, real values only.

Reads KEY=VALUE lines from ../.env (repo root) and exports them via os.environ
without printing values. No silent fallbacks: missing keys raise when read.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / '.env'

_REQUIRED = ('DATABASE_URL', 'OPENROUTER_API_KEY', 'EMBEDDING_MODEL')


def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    """Parse .env into os.environ (existing env wins); return loaded keys."""
    if not path.exists():
        raise FileNotFoundError(
            f'thiếu {path}: tạo từ .env Day 6 (DATABASE_URL, OPENROUTER_API_KEY, '
            f'EMBEDDING_MODEL) và thêm OPENROUTER_MODEL cho agent')
    loaded: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if not key:
            continue
        loaded[key] = value
        os.environ.setdefault(key, value)
    missing = [k for k in _REQUIRED if k not in loaded and not os.environ.get(k)]
    if missing:
        raise ValueError(f'.env thiếu các khóa: {", ".join(missing)}')
    return loaded


def require(key: str) -> str:
    value = os.environ.get(key, '').strip()
    if not value:
        raise ValueError(f'biến môi trường {key} chưa được đặt (kiểm tra .env)')
    return value

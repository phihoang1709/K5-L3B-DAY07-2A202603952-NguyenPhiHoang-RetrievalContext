"""Build the advanced index: text + table + figure-description chunks in pgvector.

Chunk sources (advanced/data/):
- pages.json           page text -> paragraph-ish windows <=900 chars, deterministic IDs
- tables.json          one chunk per table: "Bảng (trang N):" + rows text
- figure_descriptions.json  one chunk per described figure, prefixed [Trang N | Loại: ...]

All chunks share the basic-part chunk schema (id/text/source_id/source/page/metadata)
so run_agent / pack_context / the controller work unchanged. Vectors go to the
day7adv_ table namespace (never touches Day 6 data); strategy name 'adv_c1'.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'starter'))
from day6_bridge import DAY6, MyEmbedder, PgVectorStore  # noqa: E402
from day7_env import load_env, require  # noqa: E402

Chunk = DAY6['models'].Chunk

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / 'data'
STRATEGY = 'adv_c1'
TABLE_PREFIX = 'day7adv_'
PAGE_WINDOW = 900
PAGE_OVERLAP = 150

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'starter'))


def chunk_id(page: int, kind: str, ordinal: int, start: int, end: int) -> str:
    digest = hashlib.sha256(
        f"vcb_ar_2024|{page}|{kind}|{ordinal}|{start}|{end}".encode('utf-8')).hexdigest()
    return digest[:16]


def page_chunks(pages: list[dict]) -> list[dict]:
    out = []
    for entry in pages:
        page = entry['page']
        text = entry['text']
        start = 0
        ordinal = 0
        while start < len(text):
            end = min(start + PAGE_WINDOW, len(text))
            piece = text[start:end]
            if piece.strip():
                ordinal += 1
                out.append({'id': chunk_id(page, 'text', ordinal, start, end),
                            'text': piece.strip(), 'source_id': 'vcb_ar_2024',
                            'source': 'vcb_ar_2024.pdf', 'page': page,
                            'metadata': {'kind': 'text', 'start_offset': start,
                                         'end_offset': end}})
            if end >= len(text):
                break
            start += PAGE_WINDOW - PAGE_OVERLAP
    return out


def main():
    load_env()
    pages = json.loads((DATA_DIR / 'pages.json').read_text(encoding='utf-8'))
    tables = json.loads((DATA_DIR / 'tables.json').read_text(encoding='utf-8'))
    desc_by_id: dict = {}
    for path in sorted(DATA_DIR.glob('figure_descriptions*.json')):
        for row in json.loads(path.read_text(encoding='utf-8')):
            desc_by_id.setdefault(row['id'], row)
    figures = json.loads((DATA_DIR / 'figures.json').read_text(encoding='utf-8'))
    print(json.dumps({'described_figures': len(desc_by_id)}, ensure_ascii=False))

    chunks = page_chunks(pages)
    for table in tables:
        chunks.append({'id': chunk_id(table['page'], 'table', 0, 0, table['n_rows']),
                       'text': f"Bảng (trang {table['page']}):\n{table['text']}",
                       'source_id': 'vcb_ar_2024', 'source': 'vcb_ar_2024.pdf',
                       'page': table['page'],
                       'metadata': {'kind': 'table', 'n_rows': table['n_rows']}})
    figures_described = 0
    for figure in figures:
        d = desc_by_id.get(figure['id'])
        if not d or not d.get('description'):
            continue
        figures_described += 1
        chunks.append({'id': chunk_id(figure['page'], 'figure', 0, 0, len(d['description'])),
                       'text': f"[Trang {figure['page']} | Loại: {figure['kind']}] {d['description']}",
                       'source_id': 'vcb_ar_2024', 'source': 'vcb_ar_2024.pdf',
                       'page': figure['page'],
                       'metadata': {'kind': figure['kind'], 'crop': figure['crop'],
                                    'bbox': figure['bbox'], 'area_ratio': figure['area_ratio']}})
    ids = [c['id'] for c in chunks]
    if len(set(ids)) != len(ids):
        raise ValueError('chunk ID trùng')
    print(json.dumps({'text_chunks': sum(1 for c in chunks if c['metadata']['kind'] == 'text'),
                      'table_chunks': sum(1 for c in chunks if c['metadata']['kind'] == 'table'),
                      'figure_chunks': sum(1 for c in chunks if c['metadata']['kind'] in ('chart', 'image')),
                      'total': len(chunks)}, ensure_ascii=False))

    # de-duplicate identical text on the same page (windows can repeat on short pages)
    seen = set()
    unique_chunks = []
    for c in chunks:
        key = (c['page'], c['metadata']['kind'], c['text'])
        if key in seen:
            continue
        seen.add(key)
        unique_chunks.append(c)
    print(json.dumps({'after_dedup': len(unique_chunks)}, ensure_ascii=False))

    embedder = MyEmbedder()
    store = PgVectorStore(require('DATABASE_URL'), tables_prefix=TABLE_PREFIX)
    store.create_schema()
    batch = 48
    for i in range(0, len(unique_chunks), batch):
        group = unique_chunks[i:i + batch]
        vectors = embedder.embed_documents([c['text'] for c in group])
        store.upsert(STRATEGY, [
            Chunk(chunk_id=c['id'], document_id=c['source_id'], source=c['source'],
                  page=c['page'], text=c['text'], metadata=c['metadata'],
                  start_offset=c['metadata'].get('start_offset'),
                  end_offset=c['metadata'].get('end_offset')) for c in group], vectors,
            model_name=embedder.model_name, served_model=embedder.served_model,
            config={'chunking': 'page-window-900/150', 'corpus': 'vcb_ar_2024'})
        print(f'[{i + len(group)}/{len(unique_chunks)}] upserted', flush=True)
        time.sleep(0.5)

    (DATA_DIR / 'chunks_adv.json').write_text(
        json.dumps(unique_chunks, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    meta = store.get_strategy_meta(STRATEGY)
    print(json.dumps({'strategy': STRATEGY, 'meta_dimensions': meta['dimensions'],
                      'model': meta['model_name']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

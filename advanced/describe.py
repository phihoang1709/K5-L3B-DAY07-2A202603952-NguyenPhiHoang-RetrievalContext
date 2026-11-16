"""Describe figure crops with gpt-4o-mini vision via OpenRouter (sharded, resumable).

Each figure region is re-rendered from the PDF at a compact size (max side
~1200px, JPEG q72) before upload, which keeps request payloads small and calls
fast. Run shards in parallel:  python describe.py --shard 0 --num-shards 4
Shard files data/figure_descriptions.shard{k}.json are merged by build_index.
Resume-safe: figures already present in ANY shard file are skipped.
"""
from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import sys
import time
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'starter'))
from day7_env import load_env, require  # noqa: E402

API_HOST = 'openrouter.ai'
API_PATH = '/api/v1/chat/completions'
HERE = Path(__file__).resolve().parent
PDF_PATH = HERE / 'data' / 'vcb_ar_2024.pdf'
FIGURES_PATH = HERE / 'data' / 'figures.json'
MODEL = os.environ.get('OPENROUTER_MODEL', 'openai/gpt-4o-mini')
MAX_TOKENS = 600
MAX_SIDE = 1200
JPEG_QUALITY = 72

PROMPT = (
    'Bạn là trợ lý trích xuất tài liệu. Ảnh này là một vùng cắt từ báo cáo thường niên '
    'Vietcombank 2024. Hãy mô tả NGẮN GỌN (tối đa 130 từ) bằng tiếng Việt đúng định dạng:\n'
    'Loại: <biểu đồ|bảng|ảnh|sơ đồ>.\n'
    'Nội dung: <tiêu đề/số hiệu nếu có; chủ đề chính>.\n'
    'Misfit: <chỉ ghi khi ảnh là trang rỗng/ảnh trang trí/không chứa thông tin hữu ích>.\n'
    'Số liệu: <các giá trị số cụ thể đọc được kèm năm/cột/hàng, ví dụ "Tổng tài sản 2024: '
    '2.741.695 tỷ đồng"; với biểu đồ liệt kê từng cột/năm rõ ràng; nếu không đọc được số, '
    'ghi "không đọc được số liệu cụ thể">.\n'
    'Không suy diễn ngoài ảnh; không bình luận.')


def describe_image(payload_text: str, image_jpeg: bytes, model: str) -> tuple[str, dict]:
    api_key = require('OPENROUTER_API_KEY')
    image_b64 = base64.b64encode(image_jpeg).decode('ascii')
    body = json.dumps({
        'model': model,
        'max_tokens': MAX_TOKENS,
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': payload_text},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{image_b64}'}},
        ]}],
    }).encode('utf-8')
    connection = http.client.HTTPSConnection(API_HOST, timeout=120)
    started = time.perf_counter()
    try:
        connection.request('POST', API_PATH, body=body, headers={
            'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'})
        response = connection.getresponse()
        raw = response.read()
    except OSError as exc:
        raise RuntimeError('vision transport lỗi') from exc
    finally:
        connection.close()
    if response.status >= 400:
        raise RuntimeError(f'vision HTTP {response.status}')
    data = json.loads(raw.decode('utf-8'))
    choices = data.get('choices') or []
    if not choices:
        raise RuntimeError('vision trả rỗng')
    usage = data.get('usage') or {}
    usage['latency_ms'] = round((time.perf_counter() - started) * 1000, 1)
    return (choices[0].get('message') or {}).get('content', '').strip(), usage


def main():
    load_env()
    parser = argparse.ArgumentParser(description='Mô tả figure crops bằng vision (shard)')
    parser.add_argument('--shard', type=int, default=0)
    parser.add_argument('--num-shards', type=int, default=1)
    args = parser.parse_args()
    figures = json.loads(FIGURES_PATH.read_text(encoding='utf-8'))
    shard_ids = {f['id'] for i, f in enumerate(figures) if i % args.num_shards == args.shard}
    shard_out = HERE / 'data' / f'figure_descriptions.shard{args.shard}.json'
    done: dict = {}
    for path in HERE.glob('data/figure_descriptions*.json'):
        for row in json.loads(path.read_text(encoding='utf-8')):
            done[row['id']] = row
    out = [done[f['id']] for f in figures
           if f['id'] in done and f['id'] in shard_ids]
    doc = pymupdf.open(PDF_PATH)
    failures = []
    pending = [f for f in figures if f['id'] in shard_ids and f['id'] not in done]
    print(json.dumps({'shard': args.shard, 'todo': len(pending)}, ensure_ascii=False),
          flush=True)
    for i, figure in enumerate(pending, 1):
        try:
            page = doc[figure['page'] - 1]
            rect = pymupdf.Rect(figure['bbox'])
            zoom = min(MAX_SIDE / max(rect.width, 1), MAX_SIDE / max(rect.height, 1), 3.0)
            zoom = max(zoom, 0.4)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=rect)
            image_jpeg = pix.tobytes('jpeg', jpg_quality=JPEG_QUALITY)
            text, usage = describe_image(PROMPT, image_jpeg, MODEL)
            out.append({'id': figure['id'], 'page': figure['page'],
                        'kind': figure['kind'], 'crop': figure['crop'],
                        'description': text, 'usage': usage})
        except (RuntimeError, OSError) as exc:
            failures.append({'id': figure['id'], 'error': str(exc)[:120]})
        if i % 10 == 0:
            shard_out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n',
                                 encoding='utf-8')
            print(f'[shard {args.shard}] {i}/{len(pending)} checkpoint', flush=True)
        time.sleep(0.2)
    shard_out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    doc.close()
    total_tokens = sum((r.get('usage') or {}).get('total_tokens', 0) for r in out)
    print(json.dumps({'shard': args.shard, 'described': len(out),
                      'failures': failures, 'total_tokens': total_tokens},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()

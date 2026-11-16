"""Extract text, tables and figure regions from the annual-report PDF.

Outputs (advanced/data/):
- pages.json    [{page, text, chars}]  (1-based physical page numbers)
- tables.json   [{id, page, n_rows, text}]  table text rows via PyMuPDF table finder
- figures.json  [{id, page, kind, bbox, crop}]  figure regions + rendered crops
- index_report.json  stats + skipped pages/regions with reasons

Usage:
  python extract.py --survey            # counts only, no files written
  python extract.py --run               # full extraction + crops (zoom 2.0)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
PDF_PATH = HERE / 'data' / 'vcb_ar_2024.pdf'
DATA_DIR = HERE / 'data'
CROPS_DIR = HERE / 'crops'
DOCUMENT_ID = 'vcb_ar_2024'
SOURCE_NAME = 'Vietcombank Annual Report 2024 (Báo cáo thường niên 2024, tiếng Việt)'

MIN_FIG_AREA_RATIO = 0.02      # ignore regions smaller than 2% of page area
MIN_FIG_WIDTH = 60             # points
MIN_FIG_HEIGHT = 50            # points
ZOOM = 2.0                     # crop render zoom (144 dpi)

CHART_KEYWORDS = ('biểu đồ', 'chart', 'graph', 'đồ thị', 'tăng trưởng', '%')


def _fig_id(page: int, kind: str, ordinal: int) -> str:
    digest = hashlib.sha256(f"{DOCUMENT_ID}|{page}|{kind}|{ordinal}".encode('utf-8')).hexdigest()
    return digest[:16]


def _classify(cluster_text: str, has_vector: bool) -> str:
    text = cluster_text.casefold()
    if any(k in text for k in ('biểu đồ', 'chart', 'graph')):
        return 'chart'
    if has_vector:
        return 'chart'   # dense vector drawings without a title are treated as charts/diagrams
    return 'image'


def survey(doc: pymupdf.Document) -> dict:
    total_tables = 0
    total_vec = 0
    total_img = 0
    pages_with_text = 0
    chart_like = 0
    for page in doc:
        text = page.get_text().strip()
        if len(text) > 200:
            pages_with_text += 1
        try:
            tables = page.find_tables()
            total_tables += len(tables.tables)
        except Exception:  # noqa: BLE001 - survey tolerates per-page failures
            pass
        try:
            clusters = page.cluster_drawings()
            total_vec += sum(1 for rect in clusters
                             if rect.width >= MIN_FIG_WIDTH and rect.height >= MIN_FIG_HEIGHT
                             and rect.width * rect.height >= MIN_FIG_AREA_RATIO * rect.get_area())
            chart_like += sum(1 for rect in clusters
                              if rect.get_area() >= 0.03 * page.rect.get_area()
                              and rect.width >= 120 and rect.height >= 80)
        except Exception:  # noqa: BLE001
            pass
        total_img += len(page.get_image_info())
    return {'pages': doc.page_count, 'pages_with_text': pages_with_text,
            'table_hits': total_tables, 'vector_clusters': total_vec,
            'raster_images': total_img, 'chart_like_regions': chart_like}


def extract(doc: pymupdf.Document) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CROPS_DIR.mkdir(parents=True, exist_ok=True)
    pages, tables, figures = [], [], []
    skipped = []
    for index, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        pages.append({'page': index, 'text': page.get_text(), 'chars': len(text)})
        if len(text) < 200:
            skipped.append({'page': index, 'reason': f'text mỏng ({len(text)} ký tự)'})
        page_area = page.rect.get_area()
        # -- tables ----------------------------------------------------------
        try:
            for ordinal, table in enumerate(page.find_tables().tables, start=1):
                extracted = table.extract()
                if not extracted:
                    continue
                rows_text = []
                for row in extracted:
                    cells = [str(cell).replace('\n', ' ').strip() if cell else '' for cell in row]
                    if any(cells):
                        rows_text.append(' | '.join(cells))
                if len(rows_text) < 2:
                    continue
                tables.append({'id': _fig_id(index, 'table', ordinal), 'page': index,
                               'n_rows': len(rows_text), 'text': '\n'.join(rows_text)})
        except Exception as exc:  # noqa: BLE001 - log per-page table failures
            skipped.append({'page': index, 'reason': f'table extract lỗi: {str(exc)[:80]}'})
        # -- figure regions ----------------------------------------------------
        rects: list[tuple[pymupdf.Rect, bool]] = []
        try:
            for rect in page.cluster_drawings():
                if (rect.width >= MIN_FIG_WIDTH and rect.height >= MIN_FIG_HEIGHT
                        and rect.get_area() >= MIN_FIG_AREA_RATIO * page_area):
                    rects.append((rect, True))
        except Exception as exc:  # noqa: BLE001
            skipped.append({'page': index, 'reason': f'cluster_drawings lỗi: {str(exc)[:80]}'})
        for info in page.get_image_info():
            bbox = info['bbox']
            rect = pymupdf.Rect(bbox)
            if (rect.width >= MIN_FIG_WIDTH and rect.height >= MIN_FIG_HEIGHT
                    and rect.get_area() >= MIN_FIG_AREA_RATIO * page_area):
                rects.append((rect, False))
        # merge overlaps (vector cluster inside raster photo etc.)
        merged: list[tuple[pymupdf.Rect, bool]] = []
        for rect, has_vector in rects:
            drop = False
            for existing in merged:
                if existing[0].intersects(rect) and (existing[0] | rect).get_area() \
                        < 1.6 * max(existing[0].get_area(), rect.get_area()):
                    union = existing[0] | rect
                    merged.remove(existing)
                    merged.append((union, existing[1] or has_vector))
                    drop = True
                    break
            if not drop:
                merged.append((rect, has_vector))
        ordinal = 0
        for rect, has_vector in sorted(merged, key=lambda r: (-r[0].get_area(), r[0].y0)):
            if rect.get_area() < 0.06 * page_area:
                skipped.append({'page': index,
                                'reason': f'vùng nhỏ bỏ qua ({rect.width:.0f}x{rect.height:.0f}pt)'})
                continue
            cluster_text = page.get_text(clip=rect)
            kind = _classify(cluster_text, has_vector)
            ordinal += 1
            fid = _fig_id(index, 'fig', ordinal)
            crop_path = f'page{index:03d}_fig{ordinal}.png'
            pix = page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM), clip=rect)
            pix.save(CROPS_DIR / crop_path)
            figures.append({'id': fid, 'page': index, 'kind': kind, 'bbox': [round(v, 1) for v in rect],
                            'crop': crop_path, 'area_ratio': round(rect.get_area() / page_area, 3),
                            'text_near': cluster_text[:200]})
        if not rects:
            pass
    return {'pages': pages, 'tables': tables, 'figures': figures, 'skipped': skipped}


def main():
    parser = argparse.ArgumentParser(description='Trích xuất PDF báo cáo thường niên')
    parser.add_argument('--survey', action='store_true', help='chỉ đếm thống kê')
    parser.add_argument('--run', action='store_true', help='trích xuất đầy đủ + crops')
    args = parser.parse_args()
    doc = pymupdf.open(PDF_PATH)
    if args.survey:
        print(json.dumps(survey(doc), ensure_ascii=False))
        return
    if not args.run:
        parser.error('chọn --survey hoặc --run')
    result = extract(doc)
    for name, obj in (('pages.json', result['pages']), ('tables.json', result['tables']),
                      ('figures.json', result['figures']), ('index_report.json', {
                          'document_id': DOCUMENT_ID, 'source': SOURCE_NAME,
                          'sha256': hashlib.sha256(PDF_PATH.read_bytes()).hexdigest(),
                          'pages': doc.page_count,
                          'n_text_pages': sum(1 for p in result['pages'] if p['chars'] >= 200),
                          'n_tables': len(result['tables']),
                          'n_figures': len(result['figures']),
                          'figures_by_kind': {k: sum(1 for f in result['figures'] if f['kind'] == k)
                                              for k in ('chart', 'image')},
                          'skipped': result['skipped'][:80]})):
        (DATA_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + '\n',
                                     encoding='utf-8')
    report = json.loads((DATA_DIR / 'index_report.json').read_text(encoding='utf-8'))
    report.pop('skipped', None)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()

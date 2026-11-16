"""Build the Day 7 benchmark from the Day 6 questions + new no-evidence items.

Sources:
- 20 answerable Vietnamese questions from Day 6 benchmark/questions.json
  (15 dev + 5 test, fields gold_source_id/gold_page/evidence_quote) mapped to
  the Day 7 schema via starter.convert_day6.convert_question.
- 4 new insufficient-evidence questions (2 dev + 2 test): near-topic questions
  whose content lives in Think Python chapters OUTSIDE the indexed corpus
  (physical pages 23-72 = chapters 1-5).

Deterministic checks before writing:
- every answerable gold evidence is contained in exactly the chunk(s) of the
  gold source/page (same rule as baseline.validate, reused);
- every no-evidence question's absence keywords appear in NO chunk;
- unique ids; exact split counts 15+2 dev, 5+2 test.

Gold stays in this label file only; retrieval/agent runners read id/split/
question/filter and never gold.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline import hit  # same hit definition as the TF-IDF baseline
from convert_day6 import convert_question

# Day 6 evidence quotes were verified against pipeline-normalized page text;
# the Day 7 matcher requires a verbatim substring of the raw chunk text, where
# PDF line breaks split some sentences (e.g. "solv-\ning"). These fixes keep the
# same source/page/sentence, truncated at the line break so they are verbatim.
EVIDENCE_FIXES = {
    'q02': 'the ability to formulate problems, think creatively',
    'q03': 'A programming language like Python that is designed to be easy for',
    'q05': 'Three kinds of errors can occur in a program: syntax errors, runtime errors, and semantic',
    'q08': 'is a named sequence of statements that performs',
    'q10': 'A box in a stack diagram that represents a function call',
    'q11': 'This chapter presents a case study that demonstrates a process for designing functions that',
    'q13': 'a many-sided polygon is a good',
    'q17': 'which divides two numbers and returns',
    'q20': 'there might be more than one frame on',
}

# Near-topic questions about chapters outside the indexed corpus (ch1-5).
# absence_keywords must appear in no chunk; the check below enforces it.
NO_EVIDENCE = [
    {'id': 'd_noev1', 'split': 'dev',
     'question': 'Theo cuốn sách, kiểu dữ liệu dictionary trong Python được giới thiệu ở chương nào và dùng để làm gì?',
     'answerable': False, 'expected_behavior': 'search_and_abstain',
     'absence_reason': 'Nội dung về dictionary thuộc chương ngoài phạm vi index (trang 23–72 chỉ gồm Chương 1–5).',
     'absence_keywords': ['dictionary']},
    {'id': 'd_noev2', 'split': 'dev',
     'question': 'Trong Python, list comprehension là gì và vì sao thường ngắn gọn hơn vòng lặp for?',
     'answerable': False, 'expected_behavior': 'search_and_abstain',
     'absence_reason': 'List comprehension không được đề cập trong phạm vi trang 23–72 của corpus.',
     'absence_keywords': ['comprehension']},
    {'id': 't_noev1', 'split': 'test',
     'question': 'Tính kế thừa (inheritance) giữa các class trong Python được cuốn sách minh họa bằng ví dụ nào?',
     'answerable': False, 'expected_behavior': 'search_and_abstain',
     'absence_reason': 'Chương về classes và inheritance nằm ngoài phạm vi index (Chương 1–5).',
     'absence_keywords': ['inheritance']},
    {'id': 't_noev2', 'split': 'test',
     'question': 'Cuốn sách dùng lệnh nào để mở và đọc nội dung một file trong Python? Cho ví dụ cú pháp.',
     'answerable': False, 'expected_behavior': 'search_and_abstain',
     'absence_reason': 'Phần xử lý file (mở/đọc) nằm ở chương ngoài phạm vi index (Chương 1–5).',
     'absence_keywords': ['open(', 'with open']},
]


def main():
    parser = argparse.ArgumentParser(description='Dựng benchmark Day 7 từ Day 6 + câu thiếu evidence')
    parser.add_argument('--day6-questions', required=True, type=Path,
                        help='benchmark/questions.json của Day 6 (object có khóa questions)')
    parser.add_argument('--chunks', required=True, type=Path, help='chunks.json đã xuất (schema Day 7)')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    raw = json.loads(args.day6_questions.read_text(encoding='utf-8'))
    day6_questions = raw['questions'] if isinstance(raw, dict) else raw
    chunks = json.loads(args.chunks.read_text(encoding='utf-8'))

    questions = [convert_question(q) for q in day6_questions]
    for q in questions:
        if q['id'] in EVIDENCE_FIXES:
            q['gold'][0]['evidence'] = EVIDENCE_FIXES[q['id']]
    # no-evidence questions carry no gold; strip label-only keys for the agent copy
    questions += [{k: v for k, v in q.items() if k != 'absence_keywords'} for q in NO_EVIDENCE]

    # -- checks ----------------------------------------------------------------
    ids = [q['id'] for q in questions]
    if len(set(ids)) != len(ids):
        raise ValueError('question ID trùng')
    for q in questions:
        if q.get('answerable') is False:
            continue
        if not any(hit(c, q['gold']) for c in chunks):
            raise ValueError(f"{q['id']}: gold không nằm trọn trong chunk đúng nguồn/trang")
    all_text = '\n'.join(c['text'] for c in chunks).casefold()
    for q in NO_EVIDENCE:
        for keyword in q['absence_keywords']:
            if keyword.casefold() in all_text:
                raise ValueError(f"{q['id']}: từ khóa {keyword!r} vẫn xuất hiện trong corpus")
    counts = {}
    for q in questions:
        key = (q['split'], q.get('answerable', True))
        counts[key] = counts.get(key, 0) + 1
    expected = {('dev', True): 15, ('dev', False): 2, ('test', True): 5, ('test', False): 2}
    if counts != expected:
        raise ValueError(f'số câu từng split không đúng: {counts} != {expected}')

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(questions, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'total': len(questions), 'counts':
                      {f'{k[0]}/{"answerable" if k[1] else "no_evidence"}': v for k, v in counts.items()}},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()

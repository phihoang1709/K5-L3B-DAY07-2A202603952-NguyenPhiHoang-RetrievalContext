# Báo cáo Day 7 — Agentic RAG

Học viên: Nguyễn Phi Hoàng · MSSV 2A202603952 · L3B · Ngày chạy 2026-11-16 (UTC)
Pipeline + chấm nhãn: học viên với hỗ trợ AI worker (RULES.md:3); mọi nhãn tay kèm lý do trong `reviews.json` cạnh trace.

## Dữ liệu và benchmark

- **Nguồn/quyền/chunk:** corpus Day 6 — *Think Python 2e, v2.4.1* (CC BY-NC 3.0), trang 23–72 (48 trang, Chương 1–5), **217 chunk** strategy **C** (paragraph ≤500 + filter `chapter`), xuất từ pgvector một lần (`starter/data/day7/chunks.json`; tái tạo theo RUNBOOK.md).
- **Store/embedding:** PostgreSQL 16.16 + pgvector 0.8.7 (bảng `day6_chunks`, cosine exact), embedding **qwen/qwen3-embedding-8b** qua OpenRouter (4096 chiều, cùng model cho index và query; `search` đối chiếu `model_identity`). Store + embedder Day 6 import nguyên vẹn qua `starter/day6_bridge.py`.
- **Agent:** `openai/gpt-4o-mini` qua OpenRouter, native tool calling (1 tool `search`), temperature 0, stdlib adapter host pin cứng. Vòng `run_agent` mặc định: ≤4 lượt search, top_k=3, budget 800 ký tự; không citation hợp lệ trong context → abstain. Transport lỗi retry 3 lần; lỗi khác ghi `status: "error"` (phiên bản controller đầu có 3 câu HTTP 400, đã sửa protocol và **chạy lại toàn bộ run** — không đắp kết quả).
- **Benchmark 24 câu = 15+2 dev / 5+2 test:** 20 câu có đáp án từ Day 6 (chuyển schema; giữ 3 câu filter do câu hỏi cung cấp) + 4 câu thiếu evidence mới (dictionary, comprehension, inheritance, xử lý file — chương ngoài phạm vi index). Absence + evidence containment kiểm chứng máy khi build (`starter/build_benchmark.py`; `EVIDENCE_FIXES` khai tường minh 9 evidence span bị PDF ngắt dòng; q15/q16 giữ quote gốc — kiểm chứng nguyên vẹn trong corpus, xem Phân tích lỗi).
- **Chấm:** grade **0/1/2** — 2 = đúng, đủ và mọi *khẳng định trung tâm* grounded (chấp nhận evidence thay thế cùng nghĩa); 1 = đúng một phần/thiếu grounding; 0 = sai hoặc từ chối câu có đáp án. `citation_support` = chunk hỗ trợ **khẳng định mà citation gắn với** (vị trí inline); gắn khẳng định ngoài corpus → false (case q03). `abstention_correct` do người chấm xác nhận. Context chấm 0/1/2 riêng 5 câu test. Gold không bao giờ vào agent/retriever.

## Retrieval và thử nghiệm

Cùng corpus, cùng 15 câu dev có đáp án (no-evidence không vào mẫu số); hit dùng `baseline.hit`, cutoff top-3 cố định.

| Cấu hình | Phương pháp, top-k, filter, budget | Giả thuyết / thay đổi | Split | Hit@1 | Evidence Hit@3 | Context Evidence Rate | Thời gian / chi phí |
|---|---|---|---|---|---|---|---|
| Baseline lexical | TF-IDF, k=3, không filter, b=800 | — | dev | 3/15 (20%) | 7/15 (46.7%) | 3/15 (20%) | ~0.1 ms/câu, offline |
| Dense (bắt buộc) | Dense store Day 6 strategy C, k=3, filter theo câu hỏi, b=800 | — | dev | 12/15 (80%) | 14/15 (93.3%) | 12/15 (80%) | median ~2.3 s/câu; 17 inputs |
| Phương pháp 3 | Hybrid RRF (dense + TF-IDF, pool 10, k=60), k=3, b=800 | — | dev | 6/15 (40%) | 11/15 (73.3%) | 6/15 (40%) | ~3.4 s/câu; 17 inputs |
| Cải thiện 1 | Hybrid RRF (như trên) | Thuật ngữ tiếng Anh trong câu hỏi VN khớp chân lexical + ngữ nghĩa cross-lingual bổ trợ qua fusion | dev | 6/15 ↓ | 11/15 ↓ | 6/15 ↓ | **Giả thuyết sai**: chân lexical quá yếu (hit1 3/15) kéo lệch fusion |
| Cải thiện 2 | Dense, k=5, b=1600 | Budget 800 cắt chunk chứa evidence (q05, q10: hit3 đúng nhưng context_hit sai); top-5 kéo thêm chunk kề | dev | 12/15 = | 14/15 = | **15/15 (100%) ↑** | ~2.6 s/câu; 17 inputs |
| Đã chọn | Dense k3 b800 (chọn ở tầng agent) | — | test | 1/5 (20%) | 2/5 (40%) | 1/5 (20%) | ~3.1 s/câu; 7 inputs |
| Baseline lexical | TF-IDF k3 b800 | — | test | 0/5 | 1/5 | 0/5 | offline |

Dense dev/test khớp tuyệt đối Day 6 strategy C — kiểm chứng nhất quán store tái dùng. TF-IDF chạy toàn bộ câu hỏi không filter (baseline lexical không có store filter).

**Hai lỗi dev** (giả thuyết đặt trước → kết luận sau đo):

1. **q05, q10 — budget cắt evidence.** Giả thuyết từ flag hit3=true ∧ context_hit=false; IMP2 xác nhận ở tầng retrieval (12/15 → 15/15). Ở tầng agent kết luận đảo: trace q05 baseline cho thấy cả 2 lượt search context chỉ có 1 chunk, gold chunk không bao giờ vào context — agent trả lời "đủ 3 loại lỗi" nhờ **tri thức ngoài corpus** (không phải "tự phục hồi bằng search lần 2"); chấm chặt → q05 baseline = **1** (IMP2 = 2, cite trọn gold chunk).
2. **q15 — lỗi ranking + query-rewrite, không phải evidence-split.** Quote gold nguyên vẹn trong chunk `9240fd620efd2d82` (p63) — phản bác nhận định "chia cắt chunk" của báo cáo Day 6 (đã flag, xem Giới hạn). Chunk không vào top-3 với query gốc; query model tự viết ("chained conditional") ở cả 2 cấu hình cũng không kéo được nó — chỉ ra glossary p69. Baseline trả lời thiếu điều kiện gold ">2 khả năng" (tri thức model) → **1**; IMP2 từ chối trung thực với context có nhưng vẫn false abstention → **0**.

**Tiêu chí chọn** (grounded answer + abstention → citation → chi phí): hai cấu hình hòa grounded mean **1.87**; baseline thắng abstention (2/2 vs 1/2), false abstention (0 vs 1) và không có hallucination khẳng định trung tâm (citation sai duy nhất q03 — gắn khẳng định ngoài corpus; IMP2 có d_noev2 hallucination + q03). Chi phí ngang nhau (42 vs 38 calls). **Chốt: dense k3 b800**; sau đó mới chạy test. Bằng chứng thứ tự chỉ là mtime (dev 09:57–10:23 < test 10:38–10:41) — không chứng minh nội dung quyết định, xem Giới hạn.

## Agent và đánh giá

| Cấu hình / split | Tool use | Số lượt gọi | Grounded 0/1/2 · trung bình | Citation hợp lệ | Câu có citation | Abstention đúng | Từ chối nhầm |
|---|---|---|---|---|---|---|---|
| Baseline k3b800 · dev | 17/17 | 25 / 17 (no-evidence dùng đủ 4) | 0→0, 1→2, 2→13 · **1.87** | 14/15 | 15/15 | 2/2 | 0/15 |
| Cải thiện 2 k5b1600 · dev | 17/17 | 21 / 17 | 0→1, 1→0, 2→14 · 1.87 | 17/19 | 15/15 | 1/2 | 1/15 |
| Đã chọn k3b800 · test | 7/7 | 15 / 7 | 0→1, 1→2, 2→2 · **1.2** | 4/4 | 4/4 | 2/2 | 1/5 |

Tổng hợp bằng `starter/agent_metrics.py`; nhãn tay có lý do từng dòng trong `reviews.json` (đã rà lại 2 lần theo trace: q05/q15 hạ 2→1 vì thiếu grounding khẳng định trung tâm; q03 citation false vì gắn câu "Java, Ruby" ngoài corpus).

**Context 0/1/2 cho 5 câu test có đáp án** (chi tiết `starter/results/context_grades_test.json`):

| Query | Gold chunk (trang) | TF-IDF baseline | Dense agent k3b800 |
|---|---|---|---|
| q16 | 721c7c474482c23c (23) | **0** — trả 0 chunk (query VN không khớp token) | **0** — context p59/p37 lệch chủ đề |
| q17 | 595589132e92b2d8 (61) | **0** — chunk chỉ giới thiệu tên "modulus", thiếu giải phép chia lấy dư | **2** — gold chunk trong context |
| q18 | 752d00fd9584ec30 (47) | **0** — glossary Ch.5 vô quan hệ | **1** — định nghĩa hàm p39, không phải glossary Ch.3 được hỏi |
| q19 | 29065825788d54be (64) | **2** — glossary Ch.5 chứa định nghĩa đầy đủ (evidence thay thế) | **2** — chunk p64 giải thích nesting qua ví dụ |
| q20 | 9ff0365884f1af78 (66) | **1** — glossary frame p48 thiếu đặc điểm gold | **1** — mở đầu 5.9 thiếu "nhiều hơn một frame" |
| **Tổng (đạt 2 / trung bình)** | | **1/5 · 0.6** | **2/5 · 1.2** |

Chấm tay theo mức đủ evidence + nguồn về ngữ nghĩa (chấp nhận locus thay thế) — bổ sung, không mâu thuẫn `context_hit` máy.

| Query ID | Loại câu | Tool call và kết quả | Câu trả lời và citation | Nhãn, lý do |
|---|---|---|---|---|
| q01 (dev) | có đáp án | 1 lượt "variable definition Python" → chunk [7d8ede3eb248d89a] p23 top-1 | "chương trình là một chuỗi các hướng dẫn chỉ định cách thực hiện một phép toán… [7d8ede3eb248d89a]" | 2/2; chunk chứa câu gold nguyên văn |
| d_noev1 (dev) | thiếu evidence | 4 lượt (dictionary/hash map/key value…) → không có nội dung | "Không đủ bằng chứng để trả lời." | abstention đúng |
| q16 (test) | có đáp án | 2 lượt query tiếng Việt → chunk p59/p37 lệch chủ đề; gold chunk p23 không vào context | "Không đủ bằng chứng để trả lời." | **0** — false abstention; lỗi ranking + query-rewrite |

- **Trace/lệnh/chi phí:** `starter/results/` (mỗi run: traces, summaries, cases, reviews, agent_summary + `context_grades_test.json`); lệnh trong RUNBOOK.md. Thời gian đo được: 380/144/144 s mỗi run. Chi phí: **không suy đoán $** — usage đo được 52k prompt + 4.2k completion tokens (3 run); embedding ≈121 inputs thành công; billed thật cần dashboard OpenRouter (chưa truy cập).
- **Trước/sau và bài học:** IMP2 nâng Context Evidence Rate 100% nhưng không chuyển hóa thành agent tốt hơn (hòa 1.87, thêm 1 hallucination d_noev2 + 1 false abstention q15); đổi lại grounding tốt đúng chỗ budget từng cắt (q05: 2 vs 1). Hai bài học: (a) context của agent sinh từ query model tự viết — khác context thí nghiệm retrieval dùng query gốc (q15: retrieval 15/15 nhưng agent cả 2 cấu hình đều thiếu gold chunk); (b) agent context hẹp có thể bù tri thức model mà chấm ban đầu không phát hiện (q05). Test: mean 1.2/2, citation 4/4, abstention 2/2, false abstention 1/5 (q16; hướng sửa: ép query tiếng Anh/kết hợp query gốc + viết lại/neighbor-chunk — ngoài phạm vi buổi chạy).
- **Giới hạn:** (1) test 5 câu — mẫu nhỏ; cả 5 tái dùng từ Day 6 (Day 6 chỉ dùng để đánh giá chunking, selection dựa trên dev; 2 câu no-evidence test mới); (2) nhãn tay học viên + AI worker — thiên lệch có thể, lý do từng dòng để đối chiếu; (3) corpus EN + câu hỏi VN là nhiễu thật (q16); (4) **mtime không chứng minh chốt-trước-test**, không có artifact freeze — tiêu chí "công bố trước" chỉ là lời khai tác giả; (5) **traces chưa commit/hash** — lịch sử bất biến chưa chứng minh được; giảm nhẹ: trace ghi một lần bởi pipeline, nhãn ở lớp reviews riêng, khuyến nghị commit ngay khi nộp; (6) chi phí thực chưa đo (cần dashboard); (7) mâu thuẫn với báo cáo Day 6 về "evidence-split" q15/q16 — cần tác giả rà lại Day 6; (8) dev agent chạy 2 lần (lỗi protocol lần đầu) — số liệu từ run cuối.

## Thử thách nâng cao (+15đ) — ĐANG DỞ, CHƯA ĐẠT BONUS

- **Tài liệu đã chọn:** *Báo cáo thường niên Vietcombank 2024* (bản tiếng Việt, 106 trang, SHA256 `9deccc35…99f8`), tải từ trang quan hệ cổ đông chính thức ([link PDF](https://www.vietcombank.com.vn/-/media/Project/VCB-Sites/VCB/Nha-Dau-tu/Files/BC-dinh-ky/BC-thuong-nien/2024/VN_VCB-Annual-Report-2024_Full_250426_FN_compressed.pdf)) — công bố đại chúng, người chấm truy cập được bản gốc. Chi tiết `advanced/doc_manifest.json`.
- **Đã xong:** trích xuất PyMuPDF — 102 trang text, **130 bảng**, **205 vùng hình** (crop PNG + bbox lưu `advanced/crops/`, `advanced/data/*.json`, `advanced/index_report.json`); vision gpt-4o-mini mô tả **91/205** figure (shard song song, resumable); `verify_benchmark.py` + benchmark dev nháp 11+3 câu (text/bảng/multi-hop — PASS verify gold); sửa tương thích ngược starter (`tables_prefix`, `system_prompt`), 15 unittest vẫn pass.
- **Còn lại (bị chặn):** hết credit tài khoản OpenRouter (HTTP 402, số dư −0.23 USD) tại bước mô tả figure 114/205 còn lại → chưa index được, chưa soạn nốt câu ảnh/biểu đồ/multi-hop figure, chưa chạy dev/test. **Chưa đạt điều kiện nhận 15đ** — không báo điểm; tiếp tục khi có credit (kế hoạch + lệnh resume trong RUNBOOK.md mục "Phần nâng cao").

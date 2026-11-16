# RUNBOOK — Day 7 Agentic RAG (2A202603952)

Hướng dẫn tái lập **từ một clone sạch** (chưa có dữ liệu local). Yêu cầu:

- Python **3.11+**, Docker Desktop (daemon đang chạy), PowerShell hoặc cmd
- Repo Day 6 cùng thư mục cha (`..\K5-L3B-DAY06-NguyenPhiHoang-2A202603952-DataIngestion`) **hoặc** biến `DAY6_REPO` trỏ tới đó — `starter/day6_bridge.py` tự tìm theo thứ tự này. `<DAY6_REPO>` trong tài liệu thay bằng đường dẫn thật
- API key OpenRouter (embeddings + chat; không có key thì các bước gọi API fail loud, không có mock)
- Lệnh viết cho PowerShell; chỗ khác biệt cmd được ghi chú. Thư mục làm việc mặc định = gốc repo Day 7 trừ khi nói rõ

## 0. Cài đặt môi trường

**Phía Day 7 (repo này):**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt    # psycopg[binary]
copy .env.example .env     # mở .env điền OPENROUTER_API_KEY thật
```

**Phía Day 6 (chỉ cần cho bước ingest ở Cách A):**

```powershell
cd <DAY6_REPO>\starter
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt    # psycopg, pypdf, python-dotenv
copy .env.example .env     # điền cùng DATABASE_URL + OPENROUTER_API_KEY + EMBEDDING_MODEL như Day 7
cd <DAY7_REPO>
```

`.env` **không bao giờ commit** (đã bị `.gitignore` — RULES.md). Các giá trị trong `.env.example` (DSN local, tên model) không phải secret; chỉ key là secret.

## 1. Vector store Day 6 (PostgreSQL + pgvector, port 55433)

Hai cách dưới đây đều tạo container tên **`day7-pgvector`** để các lệnh ở mục 2 trở đi dùng chung một tên.

**Cách A — máy sạch hoàn toàn (chưa có volume dữ liệu):**

```powershell
# (A1) Tải PDF Day 6 + kiểm tra SHA256 theo manifest (starter/data bị gitignore ở Day 6)
Invoke-WebRequest https://greenteapress.com/thinkpython2/thinkpython2.pdf `
  -OutFile <DAY6_REPO>\starter\data\thinkpython2.pdf
(Get-FileHash <DAY6_REPO>\starter\data\thinkpython2.pdf -Algorithm SHA256).Hash.ToLower()
# kỳ vọng khớp manifest: 6033000bac3f9268ad75ee041bf8e5d9a3bc8a33bb156399cbd014918cb59f94

# (A2) Tạo volume + container MỚI (volume rỗng, sẽ ingest ở bước sau)
docker run -d --name day7-pgvector -p 127.0.0.1:55433:5432 `
  -v day7_pg_data:/var/lib/postgresql/data `
  -e POSTGRES_DB=day6_lab -e POSTGRES_USER=day6 -e POSTGRES_PASSWORD=day6_local_only `
  pgvector/pgvector:0.8.7-pg16

# (A3) Ingest Day 6 (217 chunk × strategy A + B; C tái dùng vector B) ≈ 434 embedding inputs
cd <DAY6_REPO>\starter
..\.venv\Scripts\python.exe -m src.run ingest
cd <DAY7_REPO>
```

Có thể thay (A2) bằng `docker compose -p day6_student_starter up -d` chạy trong `<DAY6_REPO>\starter` — **lưu ý tên**: compose đặt tên container/volume theo project name (`-p` hoặc tên thư mục cha), ví dụ compose thường tạo `starter-postgres-1` + volume `starter_pg_data` chứ không phải `day7-pgvector`; các lệnh psql ở dưới phải đổi tên container theo đúng tên thật khi dùng compose.

**Cách B — máy đã có volume dữ liệu Day 6 (`day6_student_starter_pg_data`), bỏ qua ingest:**

```powershell
docker run -d --name day7-pgvector -p 127.0.0.1:55433:5432 `
  -v day6_student_starter_pg_data:/var/lib/postgresql/data `
  -e POSTGRES_DB=day6_lab -e POSTGRES_USER=day6 -e POSTGRES_PASSWORD=day6_local_only `
  pgvector/pgvector:0.8.7-pg16
```

**Kiểm tra (bắt buộc trước khi chạy tiếp — chỉ định container theo cách đã dùng):**

```powershell
docker exec day7-pgvector psql -U day6 -d day6_lab -c "SELECT strategy, count(*) FROM day6_chunks GROUP BY strategy;"
# kỳ vọng: A/B/C × 217
docker exec day7-pgvector psql -U day6 -d day6_lab -c "SELECT strategy, model_name, dimensions FROM day6_strategy_meta;"
# kỳ vọng: qwen/qwen3-embedding-8b, 4096
```

Cảnh báo: `docker compose up` không `-p` sẽ tạo volume rỗng mới theo tên thư mục — DB có thể trống dù container chạy; luôn chạy lệnh kiểm tra ở trên.

## 2. Xuất chunk + dựng benchmark

```powershell
cd starter
mkdir data\day7 -Force    # BẮT BUỘC từ clone sạch: thư mục chứa file export chưa tồn tại

# xuất 217 chunk strategy C (lệnh đọc pin trong psql, chỉ metadata).
# KHUYÊN DÙNG cmd cho redirect để giữ UTF-8 không BOM (redirect > của Windows PowerShell 5.1
# ghi UTF-16 làm file JSON hỏng):
cmd /c "docker exec day7-pgvector psql -U day6 -d day6_lab -A -t -c ""SELECT json_agg(row_to_json(t) ORDER BY t.id) FROM (SELECT chunk_id AS id, document_id AS source_id, source, page, text, metadata FROM day6_chunks WHERE strategy='C') t"" > data\day7\chunks.json"

# kiểm tra export parse được + đủ 217 chunk
python -c "import json; d = json.load(open('data/day7/chunks.json', encoding='utf-8')); print('chunks:', len(d))"

# benchmark 24 câu = 20 câu Day 6 (convert schema) + 4 câu thiếu evidence
# (verify evidence-containment + absence tự động; fail loud nếu hỏng)
python build_benchmark.py --day6-questions <DAY6_REPO>\benchmark\questions.json --chunks data\day7\chunks.json --output ..\data\questions.json
```

## 3. Thí nghiệm retrieval (chạy trên DEV trước)

```powershell
python retrieval_experiments.py --chunks data\day7\chunks.json --questions ..\data\questions.json --split dev --methods tfidf dense hybrid --output results\dev-retrieval
python retrieval_experiments.py --chunks data\day7\chunks.json --questions ..\data\questions.json --split dev --methods dense --top-k 5 --budget 1600 --output results\dev-retrieval-imp2-dense-k5b1600
```

## 4. Agent thật (OpenRouter + store Day 6) — chọn cấu hình trên dev rồi mới chạy test

```powershell
python dense_retriever.py                       # smoke: 1 query qua store thật
python run_agent_benchmark.py --questions ..\data\questions.json --split dev --retriever dense --top-k 3 --budget 800 --output results\dev-agent-baseline-k3b800
python run_agent_benchmark.py --questions ..\data\questions.json --split dev --retriever dense --top-k 5 --budget 1600 --output results\dev-agent-imp2-k5b1600
# ---- chỉ chạy 2 lệnh dưới SAU KHI đã chốt cấu hình và GHI LẠI quyết định (file/timestamp) ----
python retrieval_experiments.py --chunks data\day7\chunks.json --questions ..\data\questions.json --split test --methods tfidf dense --output results\test-retrieval
python run_agent_benchmark.py --questions ..\data\questions.json --split test --retriever dense --top-k 3 --budget 800 --output results\test-agent-chosen-k3b800
```

Ghi chú vận hành: lỗi transport (DNS/timeout OpenRouter) được retry 3 lần backoff 5/15/30s; lỗi khác ghi `status: "error"` trong trace — không thay bằng kết quả giả. Nếu mạng rớt giữa run, xoá thư mục output của run đó và chạy lại từ đầu (run một phần không dùng để báo cáo).

## 5. Chấm nhãn và tổng hợp

```powershell
python grading_sheet.py results\dev-agent-baseline-k3b800 ..\data\questions.json data\day7\chunks.json   # in phiếu chấm
python inspect_trace.py results\dev-agent-baseline-k3b800\traces.json ..\data\questions.json data\day7\chunks.json q05,q15   # soi trace + chunk được cite
#   -> tự chấm vào reviews.json (answer_grade 0/1/2, citation_support theo khẳng định citation gắn với, abstention_correct + notes lý do)
python agent_metrics.py --cases results\test-agent-chosen-k3b800\cases.json --traces results\test-agent-chosen-k3b800\traces.json --reviews results\test-agent-chosen-k3b800\reviews.json --split test --output results\test-agent-chosen-k3b800\agent_summary.json
```

Chấm context 0/1/2 cho 5 câu test có đáp án: đối chiếu `context_ids` cuối trong `traces.json` của 2 cấu hình với gold chunk (chunk phải chứa evidence trả lời được câu hỏi, không chỉ cùng chủ đề); ghi vào `results\context_grades_test.json` (mẫu đính kèm repo).

## 6. Kiểm tra code

```powershell
cd ..   (gốc repo)
python -m unittest discover -s tests -v    # 15 test mock pass (không đo chất lượng model thật)
```

## 7. Artifact nộp bài và trạng thái Git

**Bị `.gitignore` bỏ qua — người chấm cần các artifact sau để kiểm tra.** Quyền chia sẻ đã xác minh: corpus *Think Python 2e* là **CC BY-NC 3.0** (license trang 4 của PDF); chunk ≤500 ký tự, trace/benchmark chỉ chứa trích dẫn từ sách + nhãn chấm — chia sẻ được cho mục đích giáo dục phi thương mại với ghi công (đã có trong báo cáo); quét secret trên toàn bộ `starter/results`, `data`, tài liệu (**0 kết quả** với `sk-or`, `sk-ant`, `OPENROUTER_API_KEY`); không có PII.

```powershell
# nộp kèm artifact (ép thêm file bị ignore):
git add -f starter/data/day7/chunks.json `
  starter/results/dev-retrieval `
  starter/results/dev-retrieval-imp2-dense-k5b1600 `
  starter/results/test-retrieval `
  starter/results/dev-agent-baseline-k3b800 `
  starter/results/dev-agent-imp2-k5b1600 `
  starter/results/test-agent-chosen-k3b800 `
  starter/results/context_grades_test.json
git status   # kiểm lại trước commit: .env và smoke-agent KHÔNG được xuất hiện
```

Không nộp: `starter/results/smoke-agent` (smoke test nội bộ), `.env` (chứa API key — tuyệt đối không). Nếu không muốn nộp artifact, RUNBOOK này chính là "cách tái tạo" được SUBMISSION.md chấp nhận.

**Chưa được track (cần `git add` thường):** `data/questions.json`, các script `starter/*.py` mới, `report/individual/2A202603952_NguyenPhiHoang.md`, `RUNBOOK.md`, `requirements.txt`, `.env.example`.

## Cấu trúc kết quả

`starter/results/<run>/`: `traces.json` (mọi tool call/query/context/answer/citation/usage theo câu — **không bao giờ sửa tay**), `summary.json`|`run_summary.json`, `cases.json`, `review_template.json` (phiếu chấm), `reviews.json` (nhãn + lý do từng câu), `agent_summary.json` (tổng hợp `agent_metrics.py`), `grading_sheet.txt`.

## 8. Phần nâng cao — ADVANCED.md (thư mục `advanced/`, ĐANG DỞ)

Trạng thái hiện tại: đã tải + trích xuất tài liệu, mô tả vision **91/205** figure; **tạm dừng do hết credit OpenRouter (HTTP 402)** — chưa index, chưa chạy benchmark nâng cao, **chưa đạt điều kiện nhận 15đ**. Lệnh dưới để resume khi có credit.

```powershell
cd advanced
# (A1) tải PDF (nếu chưa có) + kiểm tra SHA256
Invoke-WebRequest https://www.vietcombank.com.vn/-/media/Project/VCB-Sites/VCB/Nha-Dau-tu/Files/BC-dinh-ky/BC-thuong-nien/2024/VN_VCB-Annual-Report-2024_Full_250426_FN_compressed.pdf -OutFile data\vcb_ar_2024.pdf
(Get-FileHash data\vcb_ar_2024.pdf -Algorithm SHA256).Hash.ToLower()
# kỳ vọng: 9deccc3518e23302d00353b4d371a9dd251b67b12f9fe58a4da4ad3c727e99f8

# (A2) trích xuất text/bảng/figure crops (đã chạy; idempotent)
python extract.py --survey
python extract.py --run

# (A3) mô tả figure bằng vision — SHARD song song, resume-safe (bị chặn ở đây, thiếu credit)
python describe.py --shard 0 --num-shards 4    # chạy 4 tiến trình shard 0..3 song song
# hoặc tuần tự: for /l %k in (0,1,3) do python describe.py --shard %k --num-shards 4

# (A4) build index pgvector day7adv_ (strategy adv_c1; ĐÚNG MỘT LẦN sau khi đủ mô tả)
python build_index.py

# (A5) verify benchmark (hiện chỉ có dev nháp 11+3 câu; cần hoàn thiện 15+3 dev + 24+6 test)
python verify_benchmark.py
python verify_benchmark.py --search "<keyword>"   # helper tìm keyword khi soạn câu
```

Việc còn phải làm sau khi resume (theo ADVANCED.md): hoàn thiện benchmark 15+3 dev / 24+6 test phủ đủ nhóm (bảng ≥6, ảnh ≥5, biểu đồ ≥5, multi-hop ≥4, text ≥4); runner agent trên dev (2-3 cấu hình) + `config_freeze.md` chốt trước test; chạy toàn bộ test + chấm từng câu đạt/không đạt theo ADVANCED.md §3; ngưỡng nhận bonus **≥27/30 (90%)**, không làm tròn. Artifact nâng cao nằm trong `advanced/data|crops|results/` (git-ignored; `git add -f` khi nộp, quyền chia sẻ xem `doc_manifest.json`).

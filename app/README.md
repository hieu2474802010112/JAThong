# JAThong Backend — Hướng dẫn cấu trúc dự án

Tài liệu này dành cho developer mới tham gia, giải thích mục đích của từng file/thư mục trong `app/`.

---

## Sơ đồ cấu trúc

```
app/
├── main.py                        # FastAPI entry point: middleware, routes, APScheduler
├── worker.py                      # Celery task worker (gọi Gemini, ghi kết quả vào Supabase)
│
├── models/
│   └── evaluation.py              # Pydantic schemas: CVEvaluationResult, WeaknessDetail, ...
│
├── core/
│   ├── config.py                  # Env vars (GEMINI_API_KEY, REDIS_URL, SUPABASE_URL, ...)
│   ├── database.py                # Supabase client factory (singleton)
│   ├── limiter.py                 # Rate limiting middleware (per IP, per endpoint)
│   ├── logging_config.py          # JSON structured logging setup (stdout) + request_id_var
│   └── prompt_manager.py          # DB-driven prompt loader (fetches system prompt từ Supabase)
│
├── api/
│   └── v1/
│       ├── api.py                 # Router aggregator: ghép tất cả endpoints vào /api/v1
│       ├── middleware.py          # Request ID injection (ASGIRequestIDMiddleware)
│       └── endpoints/
│           ├── cv.py              # POST /cv/upload, GET /cv/result/{id}
│           ├── chat.py            # Portfolio Chatbot 1 — streaming chat API
│           └── portfolio.py       # Portfolio Builder endpoints
│
└── services/
    ├── cv_parser.py               # PDF extraction (pdfplumber + PyMuPDF fallback)
    └── ai/
        ├── prompt_templates.py    # System prompts & Rubric cấu hình (hardcoded)
        ├── evaluator.py           # ⭐ evaluate_cv() — Gemini orchestration (~80 dòng)
        ├── scorer.py              # ⭐ calculate_final_score() — Python scoring logic
        ├── classifier.py          # ⭐ check_is_cv() — CV document validation
        └── utils.py               # LLM factory (get_gemini_llm) & model cache
```

---

## Luồng xử lý CV (End-to-End)

```
[User uploads PDF]
       │
       ▼
cv.py → cv_parser.py          # 1. Parse PDF → extracted text
       │
       ▼
worker.py (Celery task)        # 2. Queue task và chạy background
       │
       ▼
classifier.py                  # 3. Fast-check: đây có phải CV không?
       │
       ▼
evaluator.py                   # 4. Gọi Gemini với structured output
       │
       ▼
scorer.py                      # 5. Áp dụng Python business rules:
                               #    - Career Objective Mitigation
                               #    - Portfolio exemption (HR/Sales/Logistics...)
                               #    - Social Spam check
                               #    - Weakness Caps (content quality only)
                               #    - Publication/Competition bonus
       │
       ▼
Supabase DB                    # 6. Lưu CVEvaluationResult vào ai_evaluations table
       │
       ▼
[Frontend poll GET /cv/result] # 7. Frontend nhận kết quả và render
```

---

## Các module quan trọng nhất cần đọc trước

| File | Tại sao quan trọng |
|---|---|
| [`scorer.py`](services/ai/scorer.py) | Toàn bộ logic tính điểm cuối — đây là "bộ não" của hệ thống chấm điểm |
| [`prompt_templates.py`](services/ai/prompt_templates.py) | Cấu hình Rubric chấm điểm gửi cho Gemini |
| [`models/evaluation.py`](models/evaluation.py) | Pydantic schema — thay đổi ở đây ảnh hưởng toàn bộ pipeline |
| [`worker.py`](worker.py) | Celery task config: timeout, retry, Redis |

---

## Caching Architecture

```
get_dynamic_criteria() sử dụng 3 lớp cache:

L1: TTLCache (in-process)   →  Nhanh nhất, tự hết hạn sau 24h
L2: Redis                   →  Shared across workers, tồn tại qua process restart
L3: Supabase DB             →  Source of truth, Admin có thể override rubric runtime
L4: Hardcoded fallback      →  Luôn có sẵn, không cần DB
```

---

## Biến môi trường cần thiết

Xem file `.env.example` ở root để biết toàn bộ env vars cần thiết.

| Biến | Mô tả |
|---|---|
| `GEMINI_API_KEY` | Google AI API key |
| `GEMINI_MODEL` | (Optional) Override model mặc định, VD: `gemini-2.5-flash` |
| `REDIS_URL` | Redis connection string, VD: `redis://redis:6379/0` |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (full access) |

---

## Lưu ý khi chỉnh Rubric chấm điểm

1. **Thay đổi logic Python** (mức trừ điểm, floor, cap): → sửa [`scorer.py`](services/ai/scorer.py)
2. **Thay đổi hướng dẫn cho AI** (prompt, từ khóa ngành): → sửa [`prompt_templates.py`](services/ai/prompt_templates.py)
3. **Thay đổi schema output** (thêm field mới): → sửa [`models/evaluation.py`](models/evaluation.py) **và** cập nhật frontend `evaluate.html`
4. **Override rubric runtime (không deploy)**: → Cập nhật bảng `evaluation_settings` trong Supabase với `setting_key = 'default_cv_rubric'`, sau đó gọi `clear_criteria_cache()` để invalidate cache

---

## Chạy local (development)

```bash
# 1. Khởi động toàn bộ stack (backend + worker + redis)
docker-compose up -d

# 2. Xem logs backend
docker logs cv-evaluator-backend -f

# 3. Xem logs worker
docker logs cv-evaluator-worker -f

# 4. Flower dashboard (monitor Celery tasks)
http://localhost:5555
```

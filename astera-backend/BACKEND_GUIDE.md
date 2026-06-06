# UATF Backend — Complete Developer Guide

**Stack:** FastAPI · SQLAlchemy (sync) · Neon PostgreSQL · Alembic · Python 3.12  
**Base URL:** `http://localhost:8000`  
**Swagger UI:** `http://localhost:8000/docs`

---

## How to Start the Server

```bash
cd astera-backend
uv run uvicorn main:app --reload --port 8000
```

---

## Directory Structure & What Each File Does

```
astera-backend/
│
├── main.py                          # FastAPI app entry point — CORS + router registration
│
├── database.py                      # Async engine (used by alembic/env.py only)
│
├── models.py                        # Re-export shim: `from models import Run` works from root
│
├── db/
│   ├── database.py                  # Sync SQLAlchemy engine + get_db() session (used by routes)
│   └── models.py                    # All 4 ORM table definitions
│
├── routes/
│   ├── suites.py                    # 4 suite endpoints (GET all, POST, GET one, DELETE)
│   └── runs.py                      # 7 run endpoints (start, status, report, replay, compare, list)
│
├── services/
│   ├── adapters/
│   │   ├── base.py                  # Abstract BaseAgentAdapter class
│   │   ├── factory.py               # AdapterFactory.create(model_type) → adapter instance
│   │   ├── gemini_adapter.py        # Gemini 2.0 Flash via google-generativeai SDK
│   │   ├── openai_adapter.py        # GPT-4-Turbo via OpenRouter REST API (httpx)
│   │   └── claude_adapter.py        # Claude 3.5 Sonnet via OpenRouter (inherits OpenAI adapter)
│   │
│   ├── test_runner.py               # Core orchestrator: execute_run() drives adapters + assertions
│   ├── llm_judge.py                 # Gemini-as-judge: scores actual vs golden response (0–100)
│   └── judge.py                     # Shim: maps test_runner kwarg names → llm_judge params
│
├── alembic/
│   ├── env.py                       # Async-compatible alembic config, reads DATABASE_URL from .env
│   └── versions/                    # Auto-generated migration files
│
└── .env                             # Secret keys — NEVER commit
```

---

## Environment Variables (`.env`)

| Variable | Example | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://user:pass@host/db?sslmode=require` | Neon PostgreSQL connection |
| `GEMINI_API_KEY` | `AIzaSy...` | Google AI Studio key for Gemini adapter + judge |
| `OPENROUTER_API_KEY` | `sk-or-...` | OpenRouter key for GPT-4 and Claude |
| `FRONTEND_URL` | `http://localhost:3000` | Allowed CORS origin |
| `HOST` | `0.0.0.0` | Uvicorn bind host |
| `PORT` | `8000` | Uvicorn port |
| `GEMINI_JUDGE_MODEL` | `gemini-3.1-flash-lite` | Model used by llm_judge (optional, has default) |

---

## Database Schema (4 Tables)

### `test_suites`
| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `name` | VARCHAR(255) | Suite display name |
| `description` | TEXT | Optional description |
| `multi_model_test` | BOOLEAN | True = test all listed models |
| `models_to_test` | JSON | e.g. `["gemini", "gpt-4", "claude"]` |
| `default_model_type` | VARCHAR(64) | Fallback model if none specified |
| `created_at` | TIMESTAMP | Auto-set on creation |

### `test_cases`
| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `suite_id` | UUID (FK) | Parent suite |
| `prompt` | TEXT | What gets sent to the agent |
| `tools` | JSON | Tool declarations passed to the model |
| `expected_tools` | JSON | Ordered list of tool names agent should call |
| `expected_output` | TEXT | Optional exact output match |
| `golden_response` | TEXT | Ideal answer for LLM judge scoring |
| `max_steps` | INTEGER | Max tool calls allowed (default 5) |
| `order_index` | INTEGER | Display order within suite |
| `created_at` | TIMESTAMP | Auto-set on creation |

### `runs`
| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `suite_id` | UUID (FK) | Which suite was tested |
| `model_type` | VARCHAR(64) | `gemini` / `gpt-4` / `claude` / `multi` |
| `model_display_name` | VARCHAR(128) | Human-readable model name |
| `parent_run_id` | UUID (FK, nullable) | Links child runs back to parent |
| `multi_model_test` | BOOLEAN | Was this a multi-model run? |
| `models_to_test` | JSON | List of models tested |
| `status` | VARCHAR(32) | `pending` / `running` / `completed` / `failed` |
| `pass_count` | INTEGER | Tests that passed |
| `fail_count` | INTEGER | Tests that failed |
| `total_tokens` | INTEGER | Total tokens consumed |
| `execution_trace_replay` | JSON | Full flattened trace for replay view |
| `started_at` | TIMESTAMP | When execution began |
| `completed_at` | TIMESTAMP | When execution finished |
| `created_at` | TIMESTAMP | Record creation time |

### `test_results`
| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `run_id` | UUID (FK) | Parent run |
| `test_case_id` | UUID (FK) | Which test case |
| `model_used` | VARCHAR(64) | Which model produced this result |
| `final_response` | TEXT | Agent's final text output |
| `actual_response` | TEXT | Alias stored for report endpoint |
| `execution_trace` | JSON | Full step-by-step trace with divergence data |
| `token_usage` | INTEGER | Tokens used for this test case |
| `passed` | BOOLEAN | Did it pass assertions? |
| `divergence_step` | INTEGER | Step number where divergence first occurred |
| `assertion_details` | JSON | Detailed pass/fail breakdown |
| `semantic_score` | FLOAT | LLM judge score (0–100), nullable |
| `judge_explanation` | TEXT | One-sentence judge explanation |
| `created_at` | TIMESTAMP | Auto-set on creation |

---

## API Endpoints

### SUITES — `routes/suites.py`

---

#### `GET /api/suites`
Fetch all test suites with metadata.

**Request:** No body, no params.

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Invoice Agent Suite",
    "multi_model_test": true,
    "models_to_test": ["gemini", "gpt-4", "claude"],
    "test_case_count": 5,
    "last_run_status": "4/5 passed",
    "created_at": "2026-06-06T10:00:00+00:00"
  }
]
```

---

#### `POST /api/suites`
Create a new suite with test cases in one call.

**Request Body:**
```json
{
  "name": "Invoice Agent Suite",
  "multi_model_test": true,
  "models_to_test": ["gemini", "gpt-4", "claude"],
  "test_cases": [
    {
      "prompt": "Find invoice #1042 and return the total amount",
      "expected_tools": ["search_invoice", "get_invoice_details"],
      "max_steps": 5,
      "golden_response": "Invoice #1042 has a total of $5,000."
    },
    {
      "prompt": "List all overdue invoices",
      "expected_tools": ["list_invoices", "filter_by_status"],
      "max_steps": 3,
      "golden_response": null
    }
  ]
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Invoice Agent Suite",
  "multi_model_test": true,
  "models_to_test": ["gemini", "gpt-4", "claude"],
  "test_case_count": 2,
  "last_run_status": "never_run",
  "created_at": "2026-06-06T10:00:00+00:00"
}
```

---

#### `GET /api/suites/{suite_id}`
Fetch one suite with its full test case list.

**Request:** Path param `suite_id`.

**Response:**
```json
{
  "id": "uuid",
  "name": "Invoice Agent Suite",
  "multi_model_test": true,
  "models_to_test": ["gemini", "gpt-4", "claude"],
  "test_case_count": 2,
  "test_cases": [
    {
      "id": "uuid",
      "prompt": "Find invoice #1042...",
      "expected_tools": ["search_invoice", "get_invoice_details"],
      "max_steps": 5,
      "golden_response": "Invoice #1042 has a total of $5,000.",
      "order_index": 0
    }
  ],
  "created_at": "2026-06-06T10:00:00+00:00"
}
```

---

#### `DELETE /api/suites/{suite_id}`
Delete a suite and cascade-delete all its test cases, runs, and test results.

**Request:** Path param `suite_id`.

**Response:**
```json
{ "status": "deleted", "suite_id": "uuid" }
```

---

### RUNS — `routes/runs.py`

---

#### `POST /api/runs`
Start a test run. Creates one `Run` record per model and fires background tasks.  
Returns `202 Accepted` immediately — execution happens in background.

**Request Body:**
```json
{
  "suite_id": "550e8400-e29b-41d4-a716-446655440000",
  "multi_model_test": true,
  "models_to_test": ["gemini", "gpt-4", "claude"]
}
```

> For single model: `"multi_model_test": false, "models_to_test": ["gemini"]`

**Response `202`:**
```json
{
  "run_ids": [
    "run-uuid-gemini",
    "run-uuid-gpt4",
    "run-uuid-claude"
  ],
  "status": "started",
  "models_queued": ["gemini", "gpt-4", "claude"]
}
```

> Each `run_id` in the array corresponds to one model. Poll each one separately with `/status`.

---

#### `GET /api/runs`
Recent run history for the dashboard.

**Query Params:** `limit` (default 10)

**Response:**
```json
[
  {
    "run_id": "uuid",
    "suite_id": "uuid",
    "suite_name": "Invoice Agent Suite",
    "model_type": "gemini",
    "status": "completed",
    "pass_count": 4,
    "fail_count": 1,
    "started_at": "2026-06-06T10:00:00+00:00",
    "completed_at": "2026-06-06T10:02:30+00:00"
  }
]
```

---

#### `GET /api/runs/{run_id}/status`
Live poll endpoint. Call this every 2–3 seconds to track progress.

**Response:**
```json
{
  "run_id": "uuid",
  "status": "running",
  "model_type": "gemini",
  "pass_count": 2,
  "fail_count": 0,
  "total_tokens": 840,
  "trace_logs": [
    { "test_case_id": "uuid", "passed": true, "steps": 3 },
    { "test_case_id": "uuid", "passed": false, "steps": 2 }
  ],
  "started_at": "2026-06-06T10:00:00+00:00"
}
```

> `status` values: `pending` → `running` → `completed` / `failed`

---

#### `GET /api/runs/{run_id}/report`
Full completed report with all test results.

**Response:**
```json
{
  "run_id": "uuid",
  "suite_id": "uuid",
  "model_type": "gemini",
  "status": "completed",
  "pass_count": 4,
  "fail_count": 1,
  "total_tokens": 2340,
  "started_at": "...",
  "completed_at": "...",
  "results": [
    {
      "test_case_id": "uuid",
      "prompt": "Find invoice #1042...",
      "passed": true,
      "execution_trace": [...],
      "divergence_step": null,
      "semantic_score": 87.5,
      "judge_explanation": "Response is accurate and complete.",
      "token_usage": 420,
      "actual_response": "Invoice #1042 totals $5,000.",
      "expected_tools": ["search_invoice", "get_invoice_details"],
      "model_used": "gemini"
    }
  ]
}
```

---

#### `GET /api/runs/{run_id}/replay`
Agent Replay Mode — full execution trace for the DevTools-style visualiser.

**Response:**
```json
{
  "run_id": "uuid",
  "model_used": "gemini",
  "suite_name": "Invoice Agent Suite",
  "execution_trace_replay": [
    {
      "test_case_id": "uuid",
      "execution_trace": [
        {
          "step": 0,
          "tool": "search_invoice",
          "params": { "query": "invoice #1042" },
          "response": { "found": true, "amount": 5000 },
          "tokens_this_step": 120,
          "expected_tool": "search_invoice",
          "is_divergence": false,
          "divergence_reason": null
        },
        {
          "step": 1,
          "tool": "get_details",
          "params": { "id": "1042" },
          "response": { "total": 5000, "status": "paid" },
          "tokens_this_step": 95,
          "expected_tool": "get_invoice_details",
          "is_divergence": true,
          "divergence_reason": "Expected 'get_invoice_details' but model called 'get_details'"
        }
      ],
      "divergence_step": 1,
      "is_divergence": true
    }
  ],
  "pass_count": 3,
  "fail_count": 2,
  "total_tokens": 2340,
  "semantic_scores": [
    { "test_case_id": "uuid", "score": 87.5 }
  ],
  "status": "completed"
}
```

---

#### `GET /api/runs/{run_id}/compare`
Side-by-side comparison of all models tested for the same suite.

**Response:**
```json
{
  "suite_id": "uuid",
  "models": {
    "gemini": {
      "run_id": "uuid",
      "pass_count": 4,
      "fail_count": 1,
      "pass_rate": "80.0%",
      "total_tokens": 2100,
      "avg_semantic_score": 82.3,
      "status": "completed"
    },
    "gpt-4": {
      "run_id": "uuid",
      "pass_count": 3,
      "fail_count": 2,
      "pass_rate": "60.0%",
      "total_tokens": 3450,
      "avg_semantic_score": 74.1,
      "status": "completed"
    },
    "claude": {
      "run_id": "uuid",
      "pass_count": 5,
      "fail_count": 0,
      "pass_rate": "100.0%",
      "total_tokens": 1980,
      "avg_semantic_score": 91.0,
      "status": "completed"
    }
  }
}
```

---

## How a Test Run Works (End-to-End Flow)

```
Frontend
   │
   │  POST /api/runs { suite_id, models_to_test: ["gemini","gpt-4","claude"] }
   ▼
routes/runs.py  start_run()
   │  → Creates 3 Run records in DB (one per model), status="pending"
   │  → Fires 3 background tasks (one per model)
   │  → Returns { run_ids: [...] } immediately (202)
   │
   ├─── Background Task 1 (gemini) ───────────────────────────────┐
   ├─── Background Task 2 (gpt-4)  ───────────────────────────┐   │
   └─── Background Task 3 (claude) ───────────────────────┐   │   │
                                                           │   │   │
                                              services/test_runner.py  execute_run()
                                                           │
                                              AdapterFactory.create(model_type)
                                                           │
                                         ┌─────────────────┼──────────────────┐
                                         ▼                 ▼                  ▼
                                  GeminiAdapter      OpenAIAdapter       ClaudeAdapter
                                  (google SDK)       (OpenRouter)        (OpenRouter)
                                         │                 │                  │
                                         └────────────────┬┘                  │
                                                          │◄──────────────────┘
                                         adapter.run_with_trace(prompt, tools)
                                                          │
                                         Returns: { final_response, execution_trace, token_usage }
                                                          │
                                         execution_trace = [
                                           { step, tool, params, response,
                                             tokens_this_step, expected_tool,
                                             is_divergence, divergence_reason }
                                         ]
                                                          │
                                              Assertion Engine (in test_runner)
                                              → Compare actual_tools vs expected_tools
                                              → Flag divergent steps
                                              → passed = True/False
                                                          │
                                              LLM Judge (if golden_response exists)
                                              services/llm_judge.py
                                              → Gemini scores actual vs golden (0-100)
                                              → Returns score + explanation
                                                          │
                                              Save TestResult to DB
                                              Update Run: pass_count, fail_count, total_tokens
                                              Run.status = "completed"

Frontend polls GET /api/runs/{run_id}/status every 2-3 seconds
When status="completed" → fetch GET /api/runs/{run_id}/report
Click "View Replay"    → fetch GET /api/runs/{run_id}/replay
Click "Compare Models" → fetch GET /api/runs/{run_id}/compare
```

---

## Adapter Layer — How Each Model Is Called

### `services/adapters/base.py` — `BaseAgentAdapter`
Abstract class that every adapter must implement:
- `async run_with_trace(prompt, tools) → dict` — runs the agent loop
- `async get_model_name() → str` — returns display name
- `_build_step(...)` — static helper to normalise one trace step
- `_build_result(...)` — static helper to assemble the final return dict

### `services/adapters/gemini_adapter.py` — `GeminiAdapter`
- Uses `google-generativeai` SDK directly (no OpenRouter)
- Reads `GEMINI_API_KEY` from `.env`
- Starts a `chat` session, sends prompt, loops over `function_call` parts
- Sends mock `function_response` back to continue the loop
- Tokens from `response.usage_metadata.total_token_count`

### `services/adapters/openai_adapter.py` — `OpenAIAdapter`
- Uses `httpx.AsyncClient` to POST to `https://openrouter.ai/api/v1/chat/completions`
- Reads `OPENROUTER_API_KEY` from `.env`
- Default model: `gpt-4-turbo`
- Loops until `finish_reason == "stop"`, handling `tool_calls` each iteration
- Appends `role: tool` mock results to messages so the loop can continue

### `services/adapters/claude_adapter.py` — `ClaudeAdapter`
- Subclass of `OpenAIAdapter` — zero duplicated logic
- Only overrides model string: `anthropic/claude-3.5-sonnet`
- OpenRouter provides a unified OpenAI-compatible interface for Claude

### `services/adapters/factory.py` — `AdapterFactory`
```python
await AdapterFactory.create("gemini")  # → GeminiAdapter()
await AdapterFactory.create("gpt-4")   # → OpenAIAdapter(model="gpt-4-turbo")
await AdapterFactory.create("claude")  # → ClaudeAdapter(model="anthropic/claude-3.5-sonnet")
```

---

## LLM Judge — `services/llm_judge.py`

Uses Gemini to score an agent's response against a golden (ideal) answer.

**Scoring criteria:**
| Criterion | Max Points |
|---|---|
| Relevance — does it answer the prompt? | 40 |
| Factual Accuracy — matches golden facts? | 40 |
| No Hallucination — no invented info? | 20 |
| **Total** | **100** |

**Labels:** `Excellent` (80–100) · `Good` (50–79) · `Poor` (0–49)

**Called by:** `services/judge.py` (shim) → `services/test_runner.py`

---

## Assertion Engine — inside `services/test_runner.py`

Checks three things for each test case:

| Check | How |
|---|---|
| Tool sequence match | `actual_tools == expected_tools` (order matters) |
| Missing tools | Tools in expected but not called |
| Extra tools | Tools called but not in expected |
| Exact output match | Only if `expected_output` is set |

A test case **passes** only if: tool sequence matches AND no divergent steps AND output matches (when set).

---

## Database Layer

### `db/database.py` — Sync session (used by routes)
```python
from db.database import get_db
# FastAPI injects this via Depends(get_db)
# Use: db.query(Model).filter(...).all()
```

### `database.py` (root) — Async engine (used by alembic + test_runner)
```python
from database import get_db_session
# Use: async with get_db_session() as session: ...
```

### Running migrations
```bash
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

---

## Error Responses

| Scenario | HTTP Code | Response |
|---|---|---|
| Suite/Run not found | `404` | `{ "detail": "Suite not found" }` |
| Invalid model name | `422` | `{ "detail": "Unsupported model(s): ['xyz']" }` |
| Adapter crash | Run status → `failed` | Background task logs the error |
| Unhandled exception | `500` | `{ "error": "...", "status": "error" }` |

---

## Quick Test Sequence (using `/docs`)

1. `POST /api/suites` — create a suite with 2 test cases
2. Copy the returned `id`
3. `POST /api/runs` — paste `suite_id`, set `models_to_test: ["gemini"]`
4. Copy the returned `run_ids[0]`
5. `GET /api/runs/{run_id}/status` — poll until `status == "completed"`
6. `GET /api/runs/{run_id}/report` — view full results
7. `GET /api/runs/{run_id}/replay` — view step-by-step trace

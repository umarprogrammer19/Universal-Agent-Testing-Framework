# UATF — User Guide
### Universal Agent Testing Framework · Full-Stack Usage Documentation

---

## Quick Start (Run Everything)

```bash

cd astera-backend
uv sync (make sure you have installed uv on your system)
.venv\Scripts\activate
uvicorn main:app --reload --port 8000

cd astera-frontend
npm run dev
```

| Service | URL |
|---|---|
| Frontend (Dashboard) | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger UI (API Docs) | http://localhost:8000/docs |

---

## What UATF Does

UATF lets you test an AI agent against multiple LLM models (Gemini, GPT-4, Claude) in parallel and compare:
- **Which tools** the agent called
- **Whether the order matched** what you expected
- **How semantically accurate** the final response was (scored by an LLM judge)
- **Step-by-step replay** of every tool call, like browser DevTools

---

## The 5 Pages (Frontend Flow)

```
/ (Dashboard)
  └── /builder              ← Create a test suite
  └── /run/[suiteId]        ← Execute a suite (live polling)
      └── /report/[runId]   ← Full results + comparison
          └── /replay/[runId] ← DevTools-style step replay
```

---

## Page 1 — Dashboard (`/`)

**What you see:**
- **Stats bar**: Total Suites · Recent Runs · Overall Pass Rate
- **Test Suites grid**: all your suites with model badges and last-run status
- **Recent Runs panel**: last 8 runs, clickable to go to their reports

**Actions:**

| Button | What it does |
|---|---|
| `+ New Test Suite` | Navigates to `/builder` |
| `Run` (on suite card) | Calls `POST /api/runs`, navigates to `/run/[runId]` |
| `Delete` (on suite card) | Calls `DELETE /api/suites/[id]`, removes from list immediately |

**Suite card example:**
```
┌─────────────────────────────────────────┐
│ Invoice Agent Tests                     │
│ [gemini] [gpt-4] [claude] [Multi-Model] │
│ 3 test cases          ● 6/8 passed      │
│ [Run]                        [Delete]   │
└─────────────────────────────────────────┘
```

---

## Page 2 — Suite Builder (`/builder`)

**What you fill in:**

### Section 1: Suite Name
```
Suite Name: "Invoice Agent Tests"
```

### Section 2: Test Mode

**Option A — Single Model:**
```
● Single Model       ○ Multi-Model Comparison
Model dropdown: [gemini ▾]
```
Sends to backend: `models_to_test: ["gemini"]`

**Option B — Multi-Model:**
```
○ Single Model       ● Multi-Model Comparison
☑ gemini   ☑ gpt-4   ☑ claude
```
Sends to backend: `models_to_test: ["gemini", "gpt-4", "claude"]`

### Section 3: Test Cases

Each test case has 4 fields:

| Field | Example | Required |
|---|---|---|
| Trigger Prompt | `"Find invoice #1042 and return the total"` | Yes |
| Expected Tool Sequence | `"search_invoice, get_invoice_details"` | Yes |
| Max Steps | `5` | Yes (default 5) |
| Golden Response | `"Invoice #1042 has a total of $5,000."` | No |

**Golden Response** = the ideal answer. If set, the LLM judge will score the agent's actual response against it (0–100).

**Expected Tool Sequence** = comma-separated tool names **in the order you expect the agent to call them**. If the agent calls them in a different order or calls different tools, a **divergence** is recorded.

### Example: Full Suite Payload Sent to Backend

```json
POST /api/suites

{
  "name": "Invoice Agent Tests",
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
      "prompt": "List all overdue invoices for client ACME Corp",
      "expected_tools": ["list_invoices", "filter_by_client", "filter_by_status"],
      "max_steps": 8,
      "golden_response": null
    },
    {
      "prompt": "Send payment reminder to all clients with invoices over 30 days",
      "expected_tools": ["list_invoices", "filter_overdue", "send_email"],
      "max_steps": 10,
      "golden_response": "Payment reminders sent to 12 clients."
    }
  ]
}
```

**Response from backend:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Invoice Agent Tests",
  "multi_model_test": true,
  "models_to_test": ["gemini", "gpt-4", "claude"],
  "test_case_count": 3,
  "last_run_status": "never_run",
  "created_at": "2026-06-06T10:00:00+00:00"
}
```

After saving → redirects to `/` (Dashboard)

---

## Page 3 — Execution Runner (`/run/[suiteId]`)

**URL pattern:** `/run/550e8400-e29b-41d4-a716-446655440000`

### Step 1: Click "Start Run"

Frontend calls:
```json
POST /api/runs

{
  "suite_id": "550e8400-e29b-41d4-a716-446655440000",
  "models_to_test": ["gemini"],
  "multi_model_test": false
}
```

Backend responds with `202 Accepted`:
```json
{
  "run_ids": ["run-uuid-001"],
  "status": "started",
  "models_queued": ["gemini"]
}
```

### Step 2: Live Polling (every 1 second)

Frontend polls `GET /api/runs/{runId}/status` and shows:
```
[10:32:41] › Run started (id: run-uuid-001)
[10:32:42] › Steps completed: 1 — status: running
[10:32:43] › Steps completed: 3 — status: running
[10:32:45] › Steps completed: 5 — status: running
[10:32:46] › Run completed. Navigating to report…
```

**Live stats update in real-time:**
```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│      2      │  │      1      │  │    1,840    │
│ Tests Passed│  │ Tests Failed│  │ Tokens Used │
└─────────────┘  └─────────────┘  └─────────────┘
```

### Step 3: Auto-redirect

When `status === 'completed'` → automatically navigates to `/report/{runId}` after 1 second.

---

## Page 4 — Report Card (`/report/[runId]`)

**URL pattern:** `/report/run-uuid-001`

### Hero Stats
```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│      2      │  │      1      │  │    2,340    │
│   Passed    │  │   Failed    │  │   Tokens    │
└─────────────┘  └─────────────┘  └─────────────┘
```

### Tab 1 — Test Results

Each test case shows:

**Passed example:**
```
Test 1    [PASSED]    [gemini]                     Tokens: 420
"Find invoice #1042 and return the total amount"

① search_invoice → ② get_invoice_details

Score: 87.5 — Excellent
"Response is accurate and matches the invoice details."
```

**Failed (divergence) example:**
```
Test 2    [FAILED]    [gemini]                     Tokens: 380
"List all overdue invoices for client ACME Corp"

① list_invoices → ② filter_by_status  ← (red circle)

⚠ Diverged at Step 2 — Expected: filter_by_client, Got: filter_by_status
```

**Step circle colours:**
- Green circle = tool matched expected
- Red circle = divergence (wrong tool called)
- Grey circle = no expected tool set (informational only)

### Tab 2 — Model Comparison

Only useful when suite was run with `multi_model_test: true`.

**Example comparison table:**
```
Model     Pass Rate   Tokens   Avg Score   Status
────────────────────────────────────────────────────────
gemini    80.0%       2,100    82.3        COMPLETED  [View Replay]
gpt-4     60.0%       3,450    74.1        COMPLETED  [View Replay]
claude    100.0%      1,980    91.0        COMPLETED  [View Replay]
```

"View Replay" opens `/replay/{runId}?model={modelName}`

### Tab 3 — Agent Replay

Click **"Open Full Replay Mode"** → navigates to `/replay/{runId}`

---

## Page 5 — Agent Replay Mode (`/replay/[runId]`)

The "WOW" feature. Looks like browser DevTools.

**Layout: 4 columns**

```
┌──────────┬──────────────┬────────────────────────┬──────────────┐
│TEST CASES│ EXECUTION    │ STEP DETAILS           │ ANALYSIS     │
│          │ TIMELINE     │                        │              │
│ Case 1   │              │ search_invoice    [gem]│ Expected:    │
│ 3 steps  │ Step 1 ✓OK   │                        │ search_inv.. │
│          │ search_inv.. │ PARAMETERS             │              │
│⚠ Case 2  │              │ {                      │ Actual:      │
│ 5 steps  │ Step 2 ⚠DIV  │   "query": "inv #1042" │ search_inv.. │
│Diverged  │ get_details  │ }                      │              │
│          │              │                        │ TOKENS:      │
│ Case 3   │ Step 3 ✓OK   │ RESPONSE               │    120       │
│ 2 steps  │ send_email   │ {                      │              │
│          │              │   "found": true,       │ Step 1 of 3  │
└──────────┴──────────────┤   "amount": 5000       │              │
                          │ }                      │              │
                          └────────────────────────┴──────────────┘
```

### How to use Replay Mode:

| Action | How |
|---|---|
| Switch test case | Click any case in Column 1 |
| Navigate steps | Click step in Column 2 timeline |
| Step forward | Press `→` arrow key |
| Step backward | Press `←` arrow key |
| See divergence detail | Red alert in Column 4 |
| Check token cost | Amber number in Column 4 |

### What a divergence looks like in Column 4:
```
Expected Tool
search_invoice

Actual Tool
get_invoice_list   ← (shown in red)

⚠ Divergence Detected
Expected 'search_invoice' but model called 'get_invoice_list'

TOKENS THIS STEP
143

Step 2 of 5
```

---

## All Features Summary

| Feature | Where | Description |
|---|---|---|
| Create test suite | `/builder` | Name + test mode + test cases |
| Single model test | `/builder` | Pick one model from dropdown |
| Multi-model test | `/builder` | Check all 3 models — runs in parallel |
| Live execution | `/run/[suiteId]` | Real-time log + stats while agent runs |
| Tool sequence assertion | Automatic | Checks actual tools vs expected tools in order |
| Divergence detection | Report + Replay | Flags when agent called wrong tool |
| LLM Judge scoring | Report | Gemini scores actual vs golden response (0–100) |
| Full report card | `/report/[runId]` | Pass/fail per test, score, trace |
| Model comparison table | `/report` Tab 2 | Side-by-side pass rate, tokens, score |
| Agent Replay Mode | `/replay/[runId]` | DevTools-style 4-column step viewer |
| Keyboard navigation | Replay | ← → arrows to step through tool calls |
| Delete suite | Dashboard | Cascades: deletes all runs + results |
| Recent runs | Dashboard | Last 8 runs with status + click to report |
| Pass rate stat | Dashboard | Calculated across all recent runs |

---

## API Reference (Quick Cheat Sheet)

| Method | Endpoint | What it does |
|---|---|---|
| `GET` | `/api/suites` | All suites |
| `POST` | `/api/suites` | Create suite + test cases |
| `GET` | `/api/suites/{id}` | One suite with test cases |
| `DELETE` | `/api/suites/{id}` | Delete suite + cascade |
| `POST` | `/api/runs` | Start run (single or multi-model) |
| `GET` | `/api/runs` | Recent runs (dashboard) |
| `GET` | `/api/runs/{id}/status` | Poll live progress |
| `GET` | `/api/runs/{id}/report` | Full results |
| `GET` | `/api/runs/{id}/replay` | Execution trace for replay |
| `GET` | `/api/runs/{id}/compare` | Side-by-side model comparison |
| `GET` | `/health` | Backend health check |

---

## Common Payloads

### Start a Single-Model Run
```json
POST /api/runs
{
  "suite_id": "your-suite-uuid",
  "models_to_test": ["gemini"],
  "multi_model_test": false
}
```

### Start a Multi-Model Run
```json
POST /api/runs
{
  "suite_id": "your-suite-uuid",
  "models_to_test": ["gemini", "gpt-4", "claude"],
  "multi_model_test": true
}
```

### Poll Status Response
```json
GET /api/runs/{runId}/status
{
  "run_id": "run-uuid",
  "status": "running",
  "model_type": "gemini",
  "pass_count": 2,
  "fail_count": 0,
  "total_tokens": 840,
  "trace_logs": [
    { "test_case_id": "tc-uuid-1", "passed": true, "steps": 3 },
    { "test_case_id": "tc-uuid-2", "passed": true, "steps": 2 }
  ],
  "started_at": "2026-06-06T10:00:00+00:00"
}
```

### Full Report Response (abbreviated)
```json
GET /api/runs/{runId}/report
{
  "run_id": "run-uuid",
  "model_type": "gemini",
  "status": "completed",
  "pass_count": 2,
  "fail_count": 1,
  "total_tokens": 2340,
  "results": [
    {
      "test_case_id": "tc-uuid-1",
      "prompt": "Find invoice #1042...",
      "passed": true,
      "model_used": "gemini",
      "token_usage": 420,
      "semantic_score": 87.5,
      "judge_explanation": "Response is accurate and complete.",
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
          "tool": "get_invoice_details",
          "params": { "id": "1042" },
          "response": { "total": 5000, "status": "paid", "client": "ACME" },
          "tokens_this_step": 95,
          "expected_tool": "get_invoice_details",
          "is_divergence": false,
          "divergence_reason": null
        }
      ],
      "divergence_step": null,
      "actual_response": "Invoice #1042 has a total of $5,000 and is currently paid.",
      "expected_tools": ["search_invoice", "get_invoice_details"]
    }
  ]
}
```

### Replay Response (abbreviated)
```json
GET /api/runs/{runId}/replay
{
  "run_id": "run-uuid",
  "model_used": "gemini",
  "suite_name": "Invoice Agent Tests",
  "pass_count": 2,
  "fail_count": 1,
  "total_tokens": 2340,
  "execution_trace_replay": [
    {
      "test_case_id": "tc-uuid-1",
      "is_divergence": false,
      "divergence_step": null,
      "execution_trace": [ ...steps... ]
    },
    {
      "test_case_id": "tc-uuid-2",
      "is_divergence": true,
      "divergence_step": 2,
      "execution_trace": [
        {
          "step": 0, "tool": "list_invoices",
          "expected_tool": "list_invoices", "is_divergence": false, ...
        },
        {
          "step": 1, "tool": "filter_by_status",
          "expected_tool": "filter_by_client",
          "is_divergence": true,
          "divergence_reason": "Expected 'filter_by_client' but model called 'filter_by_status'"
        }
      ]
    }
  ]
}
```

### Compare Response
```json
GET /api/runs/{runId}/compare
{
  "suite_id": "suite-uuid",
  "models": {
    "gemini": {
      "run_id": "run-uuid-gemini",
      "pass_count": 4,
      "fail_count": 1,
      "pass_rate": "80.0%",
      "total_tokens": 2100,
      "avg_semantic_score": 82.3,
      "status": "completed"
    },
    "gpt-4": {
      "run_id": "run-uuid-gpt4",
      "pass_count": 3,
      "fail_count": 2,
      "pass_rate": "60.0%",
      "total_tokens": 3450,
      "avg_semantic_score": 74.1,
      "status": "completed"
    },
    "claude": {
      "run_id": "run-uuid-claude",
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

## Scoring Guide

### LLM Judge Score (0–100)

| Score | Label | Meaning |
|---|---|---|
| 80–100 | Excellent (green) | Accurate, relevant, no hallucination |
| 50–79 | Good (amber) | Mostly correct, minor gaps |
| 0–49 | Poor (red) | Inaccurate or hallucinated |

**Only appears when `golden_response` is set on the test case.**

### Scoring breakdown (internal):
```
Relevance      (0–40):  Does it answer the prompt?
Factual Match  (0–40):  Are facts correct vs golden?
No Hallucination (0–20): Did it invent anything?
───────────────────────
Total          (0–100)
```

### Pass/Fail logic

A test case **passes** only when ALL of these are true:
1. Actual tool sequence == expected tool sequence (order matters)
2. No divergent steps
3. If `expected_output` is set — response matches exactly

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Frontend shows blank / fetch errors | Make sure backend is running on port 8000 |
| `GEMINI_API_KEY` error | Add key to `astera-backend/.env` |
| `OPENROUTER_API_KEY` error | Add key to `astera-backend/.env` |
| Run stays `pending` forever | Check backend terminal for adapter errors |
| No semantic score shown | Add `golden_response` to the test case |
| Comparison tab shows "single model" | Re-run the suite with Multi-Model mode enabled |
| Replay shows no steps | Run must be `completed` before replay is available |
| Neon connection fails | Verify `DATABASE_URL` in `.env` includes `?sslmode=require` |

---

## Full User Journey (End-to-End Example)

```
1. Open http://localhost:3000

2. Click "+ New Test Suite"

3. Fill in:
   Name: "Invoice Agent Tests"
   Mode: Multi-Model Comparison (gemini + gpt-4 + claude all checked)
   
   Test Case 1:
     Prompt:         "Find invoice #1042 and return the total"
     Expected Tools: "search_invoice, get_invoice_details"
     Max Steps:      5
     Golden:         "Invoice #1042 has a total of $5,000."
   
   Test Case 2:
     Prompt:         "List all overdue invoices"
     Expected Tools: "list_invoices, filter_by_status"
     Max Steps:      3

4. Click "Save Suite" → redirected to Dashboard

5. Find your suite → click "Run"

6. Execution Runner opens → click "Start Run"
   Watch the live log update every second

7. After ~30 seconds → auto-redirected to Report Card

8. Report Card shows:
   - Hero stats (Passed / Failed / Tokens)
   - Test Results tab: each test with step timeline + scores
   - Model Comparison tab: Gemini vs GPT-4 vs Claude table
   - Agent Replay tab: click to open full replay

9. Click "Open Full Replay Mode"

10. Replay page opens:
    - Left: list of test cases (red badge on diverged ones)
    - Center: timeline of tool calls (red border on diverged steps)
    - Right-center: params + response JSON for selected step
    - Far right: expected vs actual tool, divergence reason, token count
    - Use ← → arrow keys to navigate steps
```

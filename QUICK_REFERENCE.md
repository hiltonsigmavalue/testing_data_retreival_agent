# 🗺️ Quick Reference: Execution Flow Map

## File Execution Order & Responsibilities

### 1️⃣ **STARTUP PHASE**
```
File: app/main.py
├── Creates FastAPI app instance
├── Reads config from .env (via app/config.py)
├── Mounts static files → http://localhost:8000/static/
├── Includes API router → http://localhost:8000/api/
└── Server ready for requests
```

---

### 2️⃣ **FRONTEND PHASE**
```
File: app/static/index.html
├── Displays UI when user visits http://localhost:8000/
├── User enters natural language query
│
File: app/static/app.js
├── Listens for form submission
├── Creates JSON request object (GenerateSqlRequest from app/models.py)
├── Sends POST to http://localhost:8000/api/v1/sql/generate
└── Waits for response
```

---

### 3️⃣ **REQUEST PROCESSING PHASE**

```
┌─────────────────────────────────────────────────────────────┐
│ REQUEST HITS: app/api.py → @router.post("/api/v1/sql/generate")│
└─────────────────────────────────────────────────────────────┘
         ↓
┌───────────────────────────────────────────────────────────────┐
│ DEPENDENCY: get_workflow(settings) called                      │
│ ├── Reads settings from app/config.py                         │
│ ├── Creates OpenAIJsonAgent from app/llm.py                   │
│ │   └── Initializes AsyncOpenAI client with API key           │
│ └── Creates SqlAgentWorkflow from app/workflow.py             │
└───────────────────────────────────────────────────────────────┘
         ↓
┌───────────────────────────────────────────────────────────────┐
│ MAIN ORCHESTRATION: workflow.run(query, options, context)     │
│ File: app/workflow.py → class SqlAgentWorkflow                │
│ Executes ALL 7 STAGES sequentially...                         │
└───────────────────────────────────────────────────────────────┘
```

---

### 4️⃣ **PIPELINE EXECUTION** (The Core: app/workflow.py)

Each stage follows this pattern:
```python
1. Render prompt with context
   ├─ File: app/prompt_renderer.py
   ├─ Prompts from: promt.py (stage_1, stage_1_5, etc.)
   ├─ Schema from: app/schema.py
   └─ Context from: previous stage outputs

2. Call OpenAI API
   ├─ File: app/llm.py → OpenAIJsonAgent.complete_json()
   ├─ Model: gpt-4o-mini (or custom from settings)
   ├─ Format: Strict JSON response
   └─ Extract JSON from response

3. Check status
   ├─ If needs_clarification=true → STOP, return early
   ├─ If algorithm_status="needs_clarification" → STOP
   ├─ If sql_build_status="blocked" → STOP
   └─ Else → Continue to next stage

4. Store in stages dict
   └─ └─ Used for intermediate_stages in response
```

---

### 5️⃣ **DETAILED STAGE EXECUTION**

```
┌──────────────────────────────────────────────────┐
│ STAGE 1: Intent Extraction                       │
├──────────────────────────────────────────────────┤
│ Prompt: promt.py → stage_1                       │
│ Renderer: app/prompt_renderer.py.stage_1()       │
│ Schema: app/schema.py (TRANSACTION + SPACE)      │
│ LLM Call: app/llm.py OpenAIJsonAgent            │
│ Output: OUTPUT_JSON_SCHEMA + MAPPED_JSON_SCHEMA │
│ Check: needs_clarification?                      │
└──────────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────────┐
│ STAGE 1.5: Metric Completeness                   │
│ Prompt: promt.py → stage_1_5                     │
│ Input: Stage 1 output + original query           │
│ Output: Complete metrics list                    │
│ Check: needs_clarification?                      │
└──────────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────────┐
│ STAGE 1.6: Metric Relationship                   │
│ Prompt: promt.py → stage_1_6                     │
│ Input: Stage 1.5 output + user query             │
│ Output: combined vs individual metrics           │
│ Check: needs_clarification?                      │
└──────────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────────┐
│ STAGE 2: Algorithm Creation                      │
│ Prompt: promt.py → stage_2                       │
│ Input: Stage 1.6 + full schema                   │
│ Output: Formulas, filters, grouping logic        │
│ Check: algorithm_status == "ready"?              │
└──────────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────────┐
│ STAGE 2.1: Semantic Resolver                     │
│ Prompt: promt.py → stage_2_1                     │
│ Input: Stage 2 + semantic_context from request   │
│ Output: Database-valid entity/filter values      │
│ Check: algorithm_status == "ready"?              │
└──────────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────────┐
│ STAGE 3: SQL Build                               │
│ Prompt: promt.py → stage_3                       │
│ Input: Stage 2.1 + schema                        │
│ Output: Actual SQL query string                  │
│ Check: sql_build_status == "ready"?              │
└──────────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────────┐
│ STAGE 3.1: SQL Review                            │
│ Prompt: promt.py → stage_3_1                     │
│ Input: Stage 2.1 + Stage 3 SQL                   │
│ Output: Validated SQL + review checks            │
│ Check: sql_review_status == "approved"?          │
└──────────────────────────────────────────────────┘
              ↓
         SUCCESS ✅
```

---

### 6️⃣ **RESPONSE BUILDING & RETURN**

```
File: app/workflow.py
├── Aggregate all stage outputs
├── Determine final status:
│   ├─ "completed" (if sql_review_status == "approved")
│   ├─ "needs_clarification" (if any stage needs it)
│   └─ "blocked" (if SQL not approved)
├── Create PipelineResponse (from app/models.py):
│   ├── query: original user query
│   ├── pipeline_status: completed|needs_clarification|blocked
│   ├── message: human-readable status
│   ├── stopped_at_stage: "stage_X" if stopped
│   ├── clarification_question: if needs_clarification
│   ├── sql_build_output: Stage 3 JSON (SQL query)
│   ├── sql_review_output: Stage 3.1 JSON (validation)
│   └── stages: all intermediate outputs if requested
│
├── Return from workflow.run()
└── Return from api.py endpoint
```

---

### 7️⃣ **RESPONSE SENT TO FRONTEND**

```
File: app/static/app.js
├── Receives JSON PipelineResponse
├── Parse response status
├─ if pipeline_status == "completed":
│  ├── Display: ✅ SQL Query Approved
│  └── Display: Stage outputs, SQL query
├─ if pipeline_status == "needs_clarification":
│  ├── Display: ⚠️ Clarification Needed
│  ├── Display: Clarification question
│  └── Prompt: Edit query and resubmit
└─ if pipeline_status == "blocked":
   ├── Display: ❌ Processing Failed
   └── Display: Error details and fix suggestions

File: app/static/index.html
├── Update UI with results
├── Show stage accordion details
└── Allow user to iterate or clear
```

---

## 📊 STAGE DEPENDENCY GRAPH

```
Stage 1
    ↓ (needs_clarification check)
Stage 1.5
    ↓ (needs_clarification check)
Stage 1.6
    ↓ (needs_clarification check)
Stage 2
    ↓ (algorithm_status check)
Stage 2.1
    ↓ (algorithm_status check)
Stage 3
    ↓ (sql_build_status check)
Stage 3.1
    ↓ (sql_review_status check)
Response
```

**Key**: Each stage has a checkpoint. If that checkpoint fails, execution stops and returns early.

---

## 🗝️ KEY FILES & THEIR ROLES

| File | Role | When Executed |
|------|------|---------------|
| `app/main.py` | **Entry point** | Startup (once) |
| `app/static/index.html` | **UI** | When user visits browser |
| `app/static/app.js` | **Client logic** | On user interaction |
| `app/api.py` | **API endpoint handler** | POST request received |
| `app/models.py` | **Data validation** | Request parsing |
| `app/config.py` | **Settings** | On app startup + per request |
| `app/workflow.py` | **ORCHESTRATOR** | Every POST request |
| `app/llm.py` | **LLM caller** | Every stage |
| `app/prompt_renderer.py` | **Prompt builder** | Every stage |
| `promt.py` | **Stage prompts** | Every stage |
| `app/schema.py` | **Database schema** | Every stage (injected into prompts) |

---

## 🔍 DEBUGGING: Where to Look?

### "User query seems wrong"
→ Check: `app/api.py` (endpoint), `app/models.py` (request parsing)

### "Frontend not displaying results"
→ Check: `app/static/app.js` (response parsing), `app/api.py` (response format)

### "Stage failing/clarification keeps asking"
→ Check: `promt.py` (specifically the stage_X prompt), validation logic

### "SQL is incorrect"
→ Check: `promt.py` (stage_3), `app/schema.py` (columns), `app/workflow.py` (stage 2 output)

### "OpenAI API errors"
→ Check: `app/config.py` (.env file, API key), `app/llm.py` (OpenAI client)

### "Stage outputs not showing"
→ Check: `app/static/app.js` (include_intermediate_stages flag), `app/api.py` (PipelineResponse)

---

## 📈 TYPICAL EXECUTION TIME

- **Stage 1**: ~1-2 sec (intent extraction)
- **Stage 1.5**: ~0.5-1 sec (metrics check)
- **Stage 1.6**: ~0.5-1 sec (relationship)
- **Stage 2**: ~2-3 sec (algorithm)
- **Stage 2.1**: ~1-2 sec (semantic resolution)
- **Stage 3**: ~1-2 sec (SQL build)
- **Stage 3.1**: ~1-2 sec (SQL review)

**Total**: ~8-14 seconds end-to-end (includes OpenAI API latency)

---

## 🎯 SUCCESS CRITERIA

✅ **All 7 stages complete successfully**
✅ **No clarifications needed**
✅ **SQL review approved**
✅ **Final SQL is safe (SELECT only, valid columns)**
✅ **Response returned with `pipeline_status = "completed"`**

# 🎯 Complete Application Flow Documentation

## 📊 Quick Overview

Your application is a **Real Estate SQL Agent** - an AI-powered pipeline that converts natural language real estate queries into validated SQL queries. It uses OpenAI with a sophisticated 7-stage processing pipeline.

---

## 🚀 APPLICATION ENTRY POINT

### **Startup Process: `app/main.py`**

```
🏁 Program Start
    ↓
⚙️ app/main.py
    ├── Initialize FastAPI Application
    ├── Load Settings from .env (via app/config.py)
    ├── Mount /static folder → serves frontend UI
    ├── Include API router → register endpoints
    └── Result: Server is running on http://localhost:8000
```

---

## 🌐 FRONTEND LAYER (`app/static/`)

### **Files & Responsibilities**

| File | Purpose | Key Features |
|------|---------|--------------|
| **index.html** | Landing page UI | • Text input for natural language query • Evidence JSON editor for Stage 2.1 • Display stage outputs • Results panel |
| **app.js** | Client-side logic | • Form submission • API calls to `/api/v1/sql/generate` • Parse responses • Display clarifications • Show SQL and stage outputs |
| **styles.css** | Responsive styling | • Layout & panels • Color scheme • Responsive design |

### **User Interaction Flow**
```
User Types Query in Web UI
    ↓
app.js captures form submission
    ↓
Creates GenerateSqlRequest JSON
    ↓
Sends POST to /api/v1/sql/generate
    ↓
Awaits response from API
    ↓
Displays results in UI
```

---

## 📡 API LAYER

### **Entry Endpoint: `app/api.py`**

```
POST /api/v1/sql/generate
    ├── Input: GenerateSqlRequest (user query + semantic context)
    ├── Dependency: get_workflow()
    │   ├── Creates OpenAIJsonAgent (initializes OpenAI client)
    │   └── Creates SqlAgentWorkflow (orchestrator)
    ├── Calls: workflow.run()
    └── Output: PipelineResponse (JSON with SQL or clarification)

GET /health
    └── Simple health check {"status": "ok"}
```

---

## 📋 DATA MODELS (`app/models.py`)

### **Key Models**

```python
GenerateSqlRequest:
    - query: str                          # User's natural language query
    - include_intermediate_stages: bool   # Include all stage outputs
    - semantic_context:                  # Master data for Stage 2.1
        - attribute_master_tables: dict
        - distinct_database_values: dict
        - lookup_results: dict

PipelineResponse:
    - query: str                          # Original query
    - pipeline_status: "completed" | "needs_clarification" | "blocked"
    - message: str                        # Status message
    - stopped_at_stage: str               # Which stage stopped processing
    - clarification_question: str         # If clarification needed
    - next_action: str                    # Recommended action
    - sql_build_output: dict              # Stage 3 SQL query
    - sql_review_output: dict             # Stage 3.1 review results
    - stages: dict                        # All intermediate outputs
```

---

## ⚙️ CORE PROCESSING PIPELINE

### **Main Orchestrator: `app/workflow.py` → `SqlAgentWorkflow`**

This is the **heart of your application**. It manages the 7-stage process:

```python
async def run(user_query, include_intermediate_stages, semantic_context):
    stages = {}
    
    # Execute all 7 stages in sequence
    # Each stage:
    #   1. Renders prompt with context
    #   2. Calls OpenAI API
    #   3. Parses JSON response
    #   4. Checks for clarifications
    #   5. Stores result in stages dict
    #   6. Either continues to next stage or returns clarification
    
    # Build final response
    # Return PipelineResponse
```

---

## 🔄 THE 7-STAGE PROCESSING PIPELINE

### **Stage 1: Intent Extraction** (`promt.py: stage_1`)

**File**: `promt.py`

**What It Does**:
- Validates that user provided all compulsory fields
- Extracts natural language intent into structured JSON
- Returns both `OUTPUT_JSON_SCHEMA` and `MAPPED_JSON_SCHEMA`

**Validation Rules**:
- ✅ Space entity must be valid (city_name, location_name, or micro_market)
- ✅ time_period must be explicitly specified
- ✅ transaction_category must be specified
- ✅ property_type must be specified

**Output**:
```json
{
  "OUTPUT_JSON_SCHEMA": {...},
  "MAPPED_JSON_SCHEMA": {
    "analysis_type": "...",
    "intent": "...",
    "entities": {"space_field": "..."},
    "filters": {"time_period": "...", "property_type": "...", ...},
    "needs_clarification": false
  }
}
```

**Clarification Trigger**: ❌ Missing any compulsory field

---

### **Stage 1.5: Metric Completeness Check** (`promt.py: stage_1_5`)

**What It Does**:
- Identifies ALL metrics requested in the user's original query
- Compares with metrics extracted in Stage 1
- Completes the metrics list if any were missed
- Sets completeness status

**Logic**:
1. Extract metrics from user query
2. Check against Stage 1 metrics
3. If missing metrics found → add them
4. Set `metric_completeness_status`: "complete" | "fixed" | "needs_clarification"

**Output**:
```json
{
  "metric_completeness_status": "complete",
  "metrics_requested_from_user_query": [...],
  "metrics_found_in_stage_1": [...],
  "missing_metrics_identified": [...],
  "final_metrics_list": [...]
}
```

**Clarification Trigger**: ❌ Metric meaning is ambiguous (confidence < 0.7)

---

### **Stage 1.6: Metric Calculation Relationship** (`promt.py: stage_1_6`)

**What It Does**:
- Determines if metrics should be calculated together (combined) or separately (individual)
- Based on user intent, shared entities, shared filters, grouping requirements
- Defines common grouping logic if combined

**Examples**:
- 🟢 **Combined**: "Give total sales and value of Baner, Pune for residential sale in 2024"
- 🟡 **Individual**: "Give top 4 micromarkets in Pune for rate trend, sales, and absorption"

**Output**:
```json
{
  "metric_relationship": "combined" | "individual",
  "combined_case_output": {
    "applicable": true/false,
    "metrics": [...],
    "common_entities": {...},
    "common_filters": {...}
  },
  "individual_case_output": [
    {
      "metric_name": "...",
      "filters": {...},
      "grouping": [...]
    }
  ]
}
```

**Clarification Trigger**: ❌ Relationship is unclear

---

### **Stage 2: Algorithm Creation** (`promt.py: stage_2`)

**Files**: `promt.py: stage_2`, `app/schema.py`

**What It Does**:
- Validates calculation logic for each metric
- Maps required columns from database schema
- Creates formulas (SUM, AVG, COUNT, etc.)
- Defines WHERE clause logic (filters)
- Defines GROUP BY logic (grouping)
- Creates structured steps for SQL generation

**Key Inputs**:
- Stage 1.6 output (metric relationship)
- TRANSACTION_QUERY_SCHEMA from `app/schema.py`
- SPACE_SCHEMA from `app/schema.py`

**Validation Checks**:
1. Is metric meaning clear?
2. Is calculation type clear?
3. Is there only one reasonable calculation method?

**Column Ambiguity Resolution**:
- Lists all candidate columns for each metric
- Selects best match based on:
  - Formula requirement
  - User intent
  - Filter/grouping context

**Output**:
```json
{
  "algorithm_status": "ready" | "needs_clarification",
  "calculation_logic_validation": [...],
  "column_mapping_decisions": [...],
  "final_algorithm_structure": {
    "metric_relationship": "combined" | "individual",
    "combined_algorithm": {...},
    "individual_algorithms": [...]
  }
}
```

**Blocking Condition**: ❌ Calculation logic unclear or multiple valid methods exist

---

### **Stage 2.1: Semantic Resolver** (`promt.py: stage_2_1`)

**What It Does**:
- Converts extracted entity/filter values into actual database-valid values
- Uses master tables provided in `semantic_context` parameter
- Maps ambiguous values to actual database column values
- Ensures values exist in the database

**Inputs from Flask Request**:
```json
semantic_context: {
  "attribute_master_tables": {...},    // Lookup tables
  "distinct_database_values": {...},   // Valid values per column
  "lookup_results": {...}              // Pre-computed mappings
}
```

**Example Resolution**:
- User said: "Pune"
- Database value: "Pune_City_2024" (from distinct_database_values)

**Output**: Updated algorithm with database-valid values

---

### **Stage 3: SQL Build** (`promt.py: stage_3`)

**Files**: `promt.py: stage_3`, `app/schema.py`

**What It Does**:
- Converts validated algorithm into actual SQL query
- Uses only columns from TRANSACTION_QUERY_SCHEMA
- Never invents table/column names
- Handles both combined and individual cases

**SQL Building Rules**:
- ✅ SELECT columns for metrics + grouping columns
- ✅ FROM transaction table
- ✅ WHERE clause from filters
- ✅ GROUP BY from grouping logic
- ✅ ORDER BY if sorting required

**Safety Checks**:
- ❌ No `SELECT *`
- ❌ No INSERT, UPDATE, DELETE, DROP, ALTER, etc.
- ❌ No SQL injection

**Output**:
```json
{
  "sql_build_status": "ready" | "blocked",
  "metric_relationship": "combined" | "individual",
  "combined_sql": {
    "sql_query": "SELECT ... FROM ... WHERE ...",
    "metrics_included": [...],
    "tables_used": [...],
    "columns_used": [...]
  },
  "individual_sql_queries": [...]
}
```

---

### **Stage 3.1: SQL Review & Validation** (`promt.py: stage_3_1`)

**What It Does**:
- Reviews SQL generated in Stage 3
- Validates against original algorithm
- Ensures correctness and safety

**Validation Checks**:
1. ✅ Metric relationship followed (combined/individual)?
2. ✅ Formula matches Stage 2?
3. ✅ All columns exist in schema?
4. ✅ WHERE clause matches filters?
5. ✅ GROUP BY includes all non-aggregated columns?
6. ✅ No unsafe SQL (SELECT only)?
7. ✅ Sort/rank logic correct?

**Output**:
```json
{
  "sql_review_status": "approved" | "needs_fix" | "rejected" | "blocked",
  "review_checks": {
    "sql_build_status_ready": true/false,
    "metric_relationship_followed": true/false,
    "formula_correct": true/false,
    "columns_valid": true/false,
    "filters_correct": true/false,
    "grouping_correct": true/false,
    "sorting_correct": true/false,
    "sql_safe": true/false
  },
  "approved_sql": {...},
  "errors_found": [...],
  "fix_instructions": [...]
}
```

---

## 🤖 LLM INTEGRATION (`app/llm.py`)

### **OpenAIJsonAgent Class**

```python
class OpenAIJsonAgent:
    def __init__(settings: Settings):
        # Initialize AsyncOpenAI client with API key
    
    async def complete_json(stage_name, prompt, input_context=None):
        # 1. Build messages list
        #    - System message: the stage prompt
        #    - User message: input context (optional)
        # 2. Call OpenAI API
        #    - Model: settings.openai_model (default: gpt-4o-mini)
        #    - Temperature: 0 (deterministic)
        #    - Response format: JSON
        # 3. Parse JSON response
        # 4. Validate it's a dict
        # 5. Return JSON dict
```

**Error Handling**:
- ❌ Empty response → ValueError
- ❌ Invalid JSON → ValueError
- ❌ Non-dict JSON → ValueError

---

## 📝 PROMPT TEMPLATES (`promt.py`)

Your `promt.py` file contains 7 prompt templates:

| Stage | Prompt Variable | Purpose |
|-------|-----------------|---------|
| 1 | `stage_1` | Intent extraction with validation |
| 1.5 | `stage_1_5` | Metric completeness check |
| 1.6 | `stage_1_6` | Metric relationship classification |
| 2 | `stage_2` | Algorithm creation with formulas |
| 2.1 | `stage_2_1` | Semantic value resolution |
| 3 | `stage_3` | SQL query generation |
| 3.1 | `stage_3_1` | SQL review and validation |

---

## 🎯 PROMPT RENDERER (`app/prompt_renderer.py`)

### **Responsibility**: Fill prompt templates with context

**Methods**:
```python
stage_1(user_query)                           # Inject schema + query
stage_1_5(user_query, stage_1_output)         # Include Stage 1 JSON
stage_1_6(user_query, stage_1_5_output)       # Include Stage 1.5 JSON
stage_2(stage_1_6_output)                     # Include schema + algorithm
stage_2_1_prompt()                            # Base prompt
stage_2_1_context(stage_2_out, semantic)      # Inject context + evidence
stage_3(stage_2_output)                       # Include algorithm + schema
stage_3_1(stage_2_out, stage_3_out)           # Include both
```

---

## 📊 DATABASE SCHEMA (`app/schema.py` & `schema.py`)

Two schema definitions:

### **TRANSACTION_QUERY_SCHEMA**
- Real estate transaction columns
- Metrics: `agreement_value`, `carpet_area`, etc.
- Dimensions: `transaction_date`, `property_type`, `transaction_category`, etc.
- Used: Stage 2 (algorithm), Stage 3 (SQL generation)

### **SPACE_SCHEMA**
- Geographic/space dimensions
- Fields: `city_name`, `location_name`, `micro_market`, `state`, etc.
- Used: Stage 1 (validation), Stage 2 (algorithm)

---

## 🔧 CONFIGURATION (`app/config.py`)

### **Settings Class**

```python
class Settings:
    openai_api_key: str         # From .env: OPENAI_API_KEY (required)
    openai_model: str           # From .env: OPENAI_MODEL (default: gpt-4o-mini)
    app_name: str               # Default: "Real Estate SQL Agent API"
    log_level: str              # From .env: LOG_LEVEL (default: INFO)
```

**Note**: Settings are cached with `@lru_cache` → loaded once at startup

---

## 📤 RESPONSE FLOW

### **Success Path (`pipeline_status = "completed"`)**

```
Stage 3.1 approved
    ↓
PipelineResponse created with:
    - pipeline_status = "completed"
    - message = "SQL was generated and approved"
    - sql_build_output = Stage 3 JSON
    - sql_review_output = Stage 3.1 JSON
    - stages = all intermediate outputs
    ↓
Returned to app/api.py
    ↓
Returned as JSON to frontend app.js
    ↓
Displayed in UI with SQL highlighted
```

### **Clarification Path (`pipeline_status = "needs_clarification"`)**

```
Any stage returns needs_clarification = true
    ↓
Early exit in SqlAgentWorkflow.run()
    ↓
PipelineResponse created with:
    - pipeline_status = "needs_clarification"
    - stopped_at_stage = "stage_X"
    - clarification_question = "Please provide..."
    - stages = outputs up to this point
    ↓
Returned to frontend
    ↓
app.js displays clarification question
    ↓
User edits query and resubmits
```

### **Blocked Path (`pipeline_status = "blocked"`)**

```
Any stage status = "blocked" or "needs_fix"
    ↓
PipelineResponse created with:
    - pipeline_status = "blocked"
    - error information included
    - next_action = "Inspect errors..."
    ↓
User inspects error details and adjusts
```

---

## 🧪 TESTING

### **Test Files**

| File | Purpose |
|------|---------|
| `tests/test_api.py` | Test API endpoints (/health, /api/v1/sql/generate) |
| `tests/test_workflow.py` | Test SqlAgentWorkflow execution |

---

## 🚀 HOW TO RUN

### **1. Start Backend**

```bash
# Setup environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables in .env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
LOG_LEVEL=INFO

# Run server
uvicorn app.main:app --reload
```

Backend runs on: `http://localhost:8000`

### **2. Access Frontend**

Navigate to: `http://localhost:8000/`

---

## 📋 EXECUTION CHECKLIST

**When a user submits a query:**

✅ `main.py` - FastAPI app initialized and running  
✅ Frontend `index.html` - User UI displayed  
✅ `app.js` - Captures form, builds GenerateSqlRequest  
✅ `api.py` - POST request received at /api/v1/sql/generate  
✅ `models.py` - Request validated and parsed  
✅ `workflow.py` - SqlAgentWorkflow created and run() called  
✅ `config.py` - Settings loaded (OpenAI API key, model)  
✅ `llm.py` - OpenAI client initialized  
✅ `prompt_renderer.py` - Prompts rendered with context  
✅ `promt.py` - Stage 1 prompt rendered  
✅ `schema.py` - Schema injected into prompts  
✅ OpenAI API - Called for each stage  
✅ `workflow.py` - Results aggregated and response built  
✅ `models.py` - PipelineResponse created  
✅ `api.py` - Response returned to client  
✅ `app.js` - Results parsed and displayed  

---

## 🎯 KEY TAKEAWAYS

1. **Entry Point**: `app/main.py` starts FastAPI server
2. **API Endpoint**: `POST /api/v1/sql/generate` in `app/api.py`
3. **Orchestrator**: `SqlAgentWorkflow` in `app/workflow.py` runs all stages
4. **7 Processing Stages**: Progressively transform query → SQL
5. **LLM**: OpenAI API called in each stage via `app/llm.py`
6. **Templates**: Stage prompts in `promt.py` guide LLM
7. **Schema**: `app/schema.py` defines valid columns and dimensions
8. **Response**: Returns either SQL or clarification question
9. **Frontend**: `app/static/` displays results and allows iteration

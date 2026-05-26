# Real Estate SQL Agent API

This FastAPI service runs the supplied real-estate prompt agents in dependency order and returns generated SQL plus its review. It generates and reviews `SELECT` SQL only; it does not connect to or query a database.

## Agent Flow

1. `stage_1`: extracts intent and validates required location, period, transaction category, and property type.
2. `stage_1_5`: completes the requested metric list.
3. `stage_1_6`: classifies whether metrics need combined or individual calculation.
4. `stage_2`: builds the calculation algorithm from the mapped intent.
5. `stage_2_1`: resolves entity and filter values against supplied master/database evidence.
6. `stage_3`: generates SQL from the semantically resolved algorithm.
7. `stage_3_1`: reviews SQL against the algorithm and schema.

Your existing [promt.py](promt.py) and [schema.py](schema.py) remain the source of the agent instructions and allowed database columns.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` in `.env` before calling the SQL generation endpoint. The service health route can run without it. The configured default model is `gpt-4o-mini`, the API identifier for GPT-4o mini. Each request can instead select `gpt-4o-mini` or `gpt-5.1` through its `model` field.

## Run

```powershell
uvicorn app.main:app --reload
```

API documentation is available at `http://127.0.0.1:8000/docs`.

The browser frontend is available at `http://127.0.0.1:8000/`. It provides:

- A simple query conversation area.
- A model selector for testing GPT-4o mini and GPT-5.1 runs.
- Clarification questions returned by any stopping agent stage.
- Editable Stage 2.1 semantic evidence JSON.
- Expandable JSON output for each completed stage.

## Generate And Review SQL

`/api/v1/sql/generate` accepts `POST` requests with a JSON body. Do not open
this endpoint directly in the browser address bar, because browsers send a
`GET` request.

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/sql/generate `
  -ContentType "application/json" `
  -Body '{"query":"Give total agreement value for residential sale in Pune in 2024","model":"gpt-5.1","semantic_context":{"distinct_database_values":{"city_name":["Pune"],"property_type":["residential"],"transaction_category":["sale"]}}}'
```

The response includes `sql_build_output` from Stage 3 and `sql_review_output` from Stage 3.1. Both are also printed to application logs. Stage 2 constructs the algorithm, and Stage 2.1 resolves only entity/filter values before SQL is built.

For JavaScript clients:

```javascript
await fetch("http://127.0.0.1:8000/api/v1/sql/generate", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    query: "Give total agreement value for residential sale in Pune in 2024",
    model: "gpt-4o-mini",
    semantic_context: {
      distinct_database_values: {
        city_name: ["Pune"],
        property_type: ["residential"],
        transaction_category: ["sale"]
      }
    }
  })
});
```

`semantic_context` accepts approved runtime evidence for Stage 2.1:

```json
{
  "attribute_master_tables": {},
  "distinct_database_values": {},
  "lookup_results": {}
}
```

No master-data table or database connection is present in this repository, so
the caller must currently provide this evidence. This prevents the semantic
resolver from treating invented values as database-valid values.

## Clarification Flow

When a required field, metric, metric relationship, or calculation method is
ambiguous, the pipeline returns `pipeline_status: "needs_clarification"` and
stops before SQL generation. The response identifies `stopped_at_stage`,
provides `clarification_question`, and includes `next_action`.

Example initial request:

```json
{
  "query": "Show value for residential properties in Pune"
}
```

Example response:

```json
{
  "pipeline_status": "needs_clarification",
  "stopped_at_stage": "stage_1",
  "clarification_question": "Please provide: time_period, transaction_category",
  "next_action": "Send a new POST request with one complete corrected query containing your original requirements and the clarification answer."
}
```

Submit the full clarified question, not only the answer:

```json
{
  "query": "Show total agreement value for residential sale properties in Pune in 2024"
}
```

Clarification can stop execution at:

| Stage | User clarification reason |
| --- | --- |
| `stage_1` | Location, time period, transaction category, or property type is missing/invalid. |
| `stage_1_5` | A requested metric is unclear. |
| `stage_1_6` | Whether metrics should be combined or calculated separately is unclear. |
| `stage_2` | A metric formula or schema-column mapping has more than one valid interpretation. |
| `stage_2_1` | An entity/filter value cannot be confirmed from supplied master or database evidence. |

`stage_3` builds SQL only after Stages 2 and 2.1 are ready. `stage_3_1` reviews
generated SQL; a failed review returns `pipeline_status: "blocked"` for
inspection rather than asking the user to supply missing business meaning.

## Common HTTP Messages

| Log entry | Meaning |
| --- | --- |
| `GET /health 200 OK` | The service is running normally. |
| `GET /favicon.ico 404 Not Found` | The browser requested an icon; none is configured. It does not affect the API. |
| `GET /api/v1/sql/generate 405 Method Not Allowed` | The URL was opened as `GET`; use `POST` with JSON. |
| `POST /api/v1/sql/generate 422 Unprocessable Entity` | The JSON request body is missing or invalid; it must include a non-empty `query` field. |

Send the body as a JSON object:

```json
{
  "query": "Show total agreement value for residential sale properties in Pune in 2024"
}
```

Do not wrap the complete object in quotes, as in:

```json
"{\"query\":\"Show total agreement value for residential sale properties in Pune in 2024\"}"
```

The API tolerates this double-encoded form for client compatibility, but the
object form is the correct request format.

## Test

```powershell
pip install -r requirements-dev.txt
pytest
```

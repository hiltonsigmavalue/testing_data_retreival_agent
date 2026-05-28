# Real Estate SQL Agent API

This FastAPI service runs the supplied real-estate prompt agents in dependency order, reviews generated `SELECT` SQL, executes approved SQL against a configured transaction database, and uses a bounded ReAct correction loop when probe evidence identifies a repairable issue.

## Agent Flow

1. `stage_1`: extracts intent and validates required location, period, transaction category, and property type.
2. `stage_1_5`: completes the requested metric list.
3. `stage_1_6`: classifies whether metrics need combined or individual calculation.
4. `stage_2`: builds the calculation algorithm from the mapped intent.
5. `stage_2_1`: resolves entity and filter values against supplied master/database evidence.
6. `stage_3`: generates SQL from the semantically resolved algorithm.
7. `stage_3_1`: reviews SQL against the algorithm and schema.
8. `stage_3_2`: executes only approved SQL and collects result/error and mapping evidence.
9. `stage_3_3`: observes probe evidence and decides success, no-data, fix, or failure.
10. `stage_3_4`: applies only evidence-backed SQL fixes, then returns fixed SQL to `stage_3_1`.

Stages `3.1 -> 3.2 -> 3.3 -> 3.4 -> 3.1` form a ReAct loop with a default maximum of three iterations. Every corrected SQL query must pass review again before it is executed.

Your existing [promt.py](promt.py) and [schema.py](schema.py) remain the source of the agent instructions and allowed database columns.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` in `.env` to use the OpenAI models. The configured default model is `gpt-4o-mini`, the API identifier for GPT-4o mini. Each request can select `gpt-4o-mini`, `gpt-5.1`, AWS Bedrock DeepSeek V3.2 (`deepseek.v3.2`), or AWS Bedrock Kimi K2.5 (`moonshotai.kimi-k2.5`) through its `model` field. The service health route can run without either provider configured.

To use DeepSeek V3.2 or Kimi K2.5 through Amazon Bedrock, add your Bedrock API key and region:

```dotenv
BEDROCK_API_KEY=your_bedrock_api_key_here
BEDROCK_REGION=ap-south-1
```

The app sends Bedrock requests through AWS's OpenAI-compatible `bedrock-mantle` endpoint at `https://bedrock-mantle.<region>.api.aws/v1`. Override the derived endpoint only when required:

```dotenv
BEDROCK_BASE_URL=https://bedrock-mantle.ap-south-1.api.aws/v1
```

Bedrock-hosted models may wrap a requested JSON response in Markdown fences or brief reasoning text
when invoked through Chat Completions. The backend extracts and validates the returned
JSON object before passing each stage output to the pipeline. For Bedrock
runs, the application log prints each raw response and its parsed JSON output to make
prompt-contract troubleshooting visible during testing.

Bedrock model requests send each rendered stage prompt as `user` message content,
matching AWS's Chat Completions example. OpenAI models continue using the existing
system-prompt request pattern.

To enable Stage 3.2 SQL Probe execution, configure a read-only database account:

```dotenv
TRANSACTION_DATABASE_URL=postgresql+psycopg://readonly_user:password@host:5432/transaction_db
SQL_PROBE_SAMPLE_LIMIT=25
REACT_MAX_ITERATIONS=3
```

Use the SQLAlchemy URL for your database engine and install its driver, such as
`psycopg` for PostgreSQL or `pymysql` for MySQL. The credential should have
read-only access to `transaction_db`; the application additionally rejects
non-`SELECT` SQL before execution. Probe responses report the full result count
while returning at most `SQL_PROBE_SAMPLE_LIMIT` sample rows.

## Run

For access on this computer only:

```powershell
uvicorn app.main:app --reload
```

API documentation is available at `http://127.0.0.1:8000/docs`.

The browser frontend is available at `http://127.0.0.1:8000/`. It provides:

- A simple query conversation area.
- A model selector for testing GPT-4o mini, GPT-5.1, AWS Bedrock DeepSeek V3.2, and AWS Bedrock Kimi K2.5 runs.
- Clarification questions returned by any stopping agent stage.
- A clarification answer field that reruns the complete query with the supplied answer.
- Editable Stage 2.1 semantic evidence JSON.
- Expandable JSON output for each completed stage and every ReAct iteration.
- An automatically downloaded Word-compatible stage report after each successful API execution, with a button to download the latest report again.

## Run On Wi-Fi Or LAN

To allow other computers or phones connected to the same Wi-Fi/LAN to use the
application, start Uvicorn on all network interfaces:

```powershell
.\run_lan.ps1 -Reload
```

Equivalent direct command:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

On this computer's current Ethernet network, open this URL from another
connected device:

```text
http://192.168.1.51:8000/
```

The IPv4 address can change when the router assigns a new address. The
`run_lan.ps1` script prints the current LAN URL each time it starts.

If Windows asks whether to allow Python/Uvicorn through the firewall, allow it
on **Private networks**. If the page does not open from another device, ensure
both devices are on the same network and create an inbound firewall rule for
TCP port `8000` on private networks.

Do not expose this development server directly to the public internet. The
frontend can trigger model requests using the API credentials stored on the
host machine.

## Generate And Review SQL

`/api/v1/sql/generate` accepts `POST` requests with a JSON body. Do not open
this endpoint directly in the browser address bar, because browsers send a
`GET` request.

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/sql/generate `
  -ContentType "application/json" `
  -Body '{"query":"Give total agreement value for residential sale in Pune in 2024","model":"moonshotai.kimi-k2.5","semantic_context":{"distinct_database_values":{"city_name":["Pune"],"property_type":["residential"],"transaction_category":["sale"]}}}'
```

The response includes `sql_build_output`, latest `sql_review_output`, `sql_probe_output`, `sql_observe_output`, `sql_fix_output`, and the full `react_iterations` history. Stage 2 constructs the algorithm, and Stage 2.1 resolves only entity/filter values before SQL is built and executed.

For JavaScript clients:

```javascript
await fetch("http://127.0.0.1:8000/api/v1/sql/generate", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    query: "Give total agreement value for residential sale in Pune in 2024",
    model: "moonshotai.kimi-k2.5",
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

The caller can provide evidence to the semantic resolver before SQL generation.
Once approved SQL is generated, Stage 3.2 uses the configured database
connection for execution and zero-row verification evidence.

## Clarification Flow

When a required field, metric, metric relationship, calculation method, or
later SQL decision requires user input, the pipeline returns
`pipeline_status: "needs_clarification"` and stops at that stage. The response
identifies `stopped_at_stage`, provides `clarification_question`, and includes
`next_action`.

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

In the browser UI, enter only the requested answer in the clarification answer
box; the app appends it to the original query and reruns the pipeline from
Stage 1. API callers should submit the full clarified question:

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
| `stage_3` | SQL construction returns a user-resolvable blocking clarification. |
| `stage_3_1` | SQL review returns a user-resolvable blocking clarification. |

`stage_3` builds SQL only after Stages 2 and 2.1 are ready. An approved Stage
3.1 result is executed by Stage 3.2. Stage 3.3 returns `pipeline_status:
"completed"` for data, `"no_data"` for valid execution without matching rows,
or routes database-backed correction instructions through Stage 3.4 and back
to review. A failed or exhausted loop returns `"blocked"` for inspection.

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

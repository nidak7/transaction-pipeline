# AI-Powered Transaction Processing Pipeline

Production-style backend service for asynchronously processing dirty financial transaction CSV files with FastAPI, PostgreSQL, Redis, Celery, SQLAlchemy 2.0, Alembic, Pandas, and LLM-backed classification/summary generation.

## Architecture

```mermaid
flowchart LR
    Client["Client"] --> Upload["POST /jobs/upload"]
    Upload --> Api["FastAPI"]
    Api --> JobRow["PostgreSQL Job"]
    Api --> FileStore["Uploaded CSV Volume"]
    Api --> Queue["Redis Queue"]
    Queue --> Worker["Celery Worker"]
    Worker --> Clean["Pandas Cleaning"]
    Clean --> Anomaly["Statistical + Merchant Rules"]
    Anomaly --> Classify["Batched LLM Classification"]
    Classify --> Summary["LLM JSON Summary"]
    Summary --> Results["Transactions + Summary Tables"]
    Client --> Status["GET /jobs/{id}/status"]
    Client --> Output["GET /jobs/{id}/results"]
    Status --> Results
    Output --> Results
```

## Folder Structure

```text
app/
  api/              FastAPI routers and dependencies
  core/             settings and logging
  db/               SQLAlchemy engine/session setup
  llm/              Ollama, Gemini, and fallback clients
  models/           SQLAlchemy 2.0 models
  repositories/     persistence boundary
  schemas/          Pydantic response models
  services/         cleaner, anomaly, classifier, summarizer, pipeline
  utils/            shared contracts
  workers/          Celery app and tasks
tests/
  api/
  services/
  workers/
  integration/
alembic/
docker/
scripts/
```

## Environment Variables

| Name | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL | `postgresql+psycopg://transaction:transaction@postgres:5432/transaction_pipeline` |
| `REDIS_URL` | Celery broker/result backend | `redis://redis:6379/0` |
| `OLLAMA_URL` | Ollama HTTP endpoint | `http://host.docker.internal:11434` |
| `OLLAMA_MODEL` | Ollama model name | `llama3.1` |
| `GEMINI_API_KEY` | Optional Gemini fallback key | empty |
| `GEMINI_MODEL` | Gemini fallback model | `gemini-1.5-flash` |
| `LLM_BATCH_SIZE` | Classification batch size | `25` |
| `LLM_TIMEOUT_SECONDS` | LLM HTTP timeout | `30` |
| `LLM_RETRY_BASE_DELAY_SECONDS` | Exponential backoff base delay | `1` |
| `LOG_LEVEL` | JSON log level | `INFO` |

## Setup

```bash
cp .env.example .env
docker compose up --build
```

The API is available at `http://localhost:8000`. PostgreSQL, Redis, the API, and the Celery worker run through Compose. Ollama is expected at `OLLAMA_URL`; if Ollama is unavailable and Gemini is not configured, LLM classification batches are marked `llm_failed=true` and the job still completes with deterministic summary fallbacks.

## API Examples

Health:

```bash
curl http://localhost:8000/health
```

Upload a CSV:

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -F "file=@transactions.csv"
```

List jobs with pagination and optional status filtering:

```bash
curl "http://localhost:8000/jobs?status=pending&limit=20&offset=0"
```

Poll status:

```bash
curl http://localhost:8000/jobs/{job_id}/status
```

Fetch results:

```bash
curl http://localhost:8000/jobs/{job_id}/results
```

## Processing Pipeline

1. Validate CSV shape during upload.
2. Persist a `pending` job and save the file on a shared Docker volume.
3. Enqueue a Celery task through Redis.
4. Clean rows with Pandas: ISO dates, normalized currency/status, stripped money symbols, generated missing transaction IDs, filled categories, exact duplicate removal.
5. Detect anomalies: amount greater than `3x` account median and USD usage at domestic-only merchants such as Swiggy, Ola, and IRCTC.
6. Batch uncategorized transactions for LLM classification. Calls retry 3 times with exponential backoff.
7. Generate a structured JSON summary. Invalid or unavailable LLM output falls back to deterministic totals/narrative so the job can complete.
8. Persist cleaned transactions, anomalies, LLM metadata, category spend, and `JobSummary`.

## Quality Commands

```bash
ruff check .
ruff format --check .
black --check .
mypy app
pytest
```

The test suite covers API behavior, cleaner parsing, duplicate removal, anomaly rules, LLM response parsing, retry behavior, LLM failure continuation, Celery task delegation, and an in-process end-to-end pipeline.

## Design Decisions

- FastAPI keeps the API surface explicit and OpenAPI-friendly.
- SQLAlchemy 2.0 typed models and repository methods isolate persistence from API and pipeline services.
- Alembic migrations are committed from the start to keep PostgreSQL schema changes reviewable.
- Celery workers do the heavy processing asynchronously while the client polls job state.
- LLM failures are contained at the batch/stage level. A failed classifier batch marks rows as `llm_failed`; summary failures produce deterministic fallback text.
- Structured JSON logging records job ID, stage, duration, retry attempts, and exceptions.

## Scale Notes

The first breaking points at 100x traffic would be upload volume I/O, Pandas in-memory processing, database connection pool limits, and LLM throughput. A larger production iteration would move uploaded files to object storage, shard workers by queue, stream larger CSVs, add idempotency keys, use provider-specific LLM rate limiters, and introduce observability around queue lag and stage latency.

## Future Improvements

- Add object storage for uploaded CSVs.
- Add idempotent upload keys and job cancellation.
- Add provider-specific LLM circuit breakers.
- Add Flower or Prometheus metrics for worker operations.
- Add generated API client examples.

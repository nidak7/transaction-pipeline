# Transaction Pipeline

This is a backend service that takes a messy CSV of financial transactions, cleans it in the background and sorts the transactions into categories using an LLM. You upload a file, get a job id back, and check the job until the results are ready.

## What it does

- Accepts a CSV upload and creates a job in PostgreSQL
- Cleans the data with Pandas: dates, currency, status, missing transaction ids, duplicate rows
- Flags odd transactions (an amount over 3 times the account median, or USD used at some India-only merchants)
- Sends uncategorised rows to an LLM in batches (Ollama, with Gemini as a fallback)
- Saves a summary; if the LLM fails, the job still finishes with a simple summary

## Tech used

Python, FastAPI, Celery, Redis, PostgreSQL, SQLAlchemy 2.0, Alembic, Pandas, Docker Compose, pytest

## How to run

```bash
cp .env.example .env
docker compose up --build
```

The API runs on http://localhost:8000. Ollama needs to be running on your machine for classification, or you can set a Gemini key in `.env`.

Endpoints: `GET /health`, `POST /jobs/upload`, `GET /jobs`, `GET /jobs/{id}/status`, `GET /jobs/{id}/results`.

Tests (Python 3.12):

```bash
pip install -e ".[dev]"
pytest
```

## What I would improve

- Uploaded files are kept on a Docker volume, object storage would be better
- Pandas loads the whole file in memory, so very large CSVs would be a problem
- No job cancel or duplicate upload protection yet

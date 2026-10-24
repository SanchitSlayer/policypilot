# PolicyPilot

PolicyPilot is an AI compliance copilot for B2B compliance, ops and legal teams. Upload policy and regulatory PDFs (for example the RBI KYC Master Direction or internal SOPs), ask questions in plain language, and get streamed answers with page-level citations, using OpenAI, Anthropic Claude or Google Gemini per request. A tool-calling Contract Review agent checks a contract's clauses against your stored policies and returns a structured compliance checklist, and an admin dashboard tracks requests, tokens, latency and cost per provider.

> Status: in development (Phase 1 of 7 done: document ingestion). See [CLAUDE.md](CLAUDE.md) for the roadmap.

## Tech stack

FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) + Alembic · PostgreSQL 16 + pgvector · MongoDB · Next.js (App Router) + TypeScript + Tailwind · Docker Compose · GitHub Actions · Google Cloud Run

## Run locally

Requirements: Docker Desktop (or Docker Engine with Compose v2).

```bash
cp .env.example .env          # add API keys later; not needed for Phase 0
docker compose up --build
```

| Service  | URL                            |
| -------- | ------------------------------ |
| Frontend | http://localhost:3000          |
| API      | http://localhost:8000          |
| API docs | http://localhost:8000/docs     |
| Health   | http://localhost:8000/health   |

The backend container runs `alembic upgrade head` on start (pgvector extension, documents and chunks tables).

### Ingest documents

Embeddings use OpenAI by default (`OPENAI_API_KEY`); set `EMBEDDING_PROVIDER=fake` to run fully offline.

```bash
# Upload one PDF over HTTP (doc_type: policy | contract)
curl -F "file=@sample_data/rbi_kyc.pdf" -F "doc_type=policy" http://localhost:8000/documents

# Or ingest a whole folder from the host (skips files already ingested; --force to redo)
cd backend && .venv/bin/python -m app.scripts.ingest_folder ../sample_data
```

PDFs are split per page into ~500-token chunks with 80-token overlap (configurable via `CHUNK_SIZE_TOKENS` / `CHUNK_OVERLAP_TOKENS`), so every chunk carries exactly one page number for citations.

### Backend tests (no databases needed)

```bash
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

### Frontend checks

```bash
cd frontend
npm install
npm run lint && npm run typecheck
```

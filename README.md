# PolicyPilot

PolicyPilot is an AI compliance copilot for B2B compliance, ops and legal teams. Upload policy and regulatory PDFs (for example the RBI KYC Master Direction or internal SOPs), ask questions in plain language, and get streamed answers with page-level citations, using OpenAI, Anthropic Claude or Google Gemini per request. A tool-calling Contract Review agent checks a contract's clauses against your stored policies and returns a structured compliance checklist, and an admin dashboard tracks requests, tokens, latency and cost per provider.

> Status: in development (Phases 0–4 done: ingestion, RAG chat, web UI and contract review agent). See [CLAUDE.md](CLAUDE.md) for the roadmap.

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

### Use the web app

Open http://localhost:3000:

- **Documents**: drag and drop PDFs (policy or contract); the table shows pages, chunks and live processing status.
- **Chat**: pick a provider (OpenAI, Claude, Gemini, or Fake for offline use), optionally limit the search to some documents, and ask. Answers stream in with clickable `[n]` citations; the Sources panel shows the document, page and exact passage.

### Contract review agent

Upload a contract with type **Contract**, then open **Contract Review**, pick it and a provider, and click **Run review**. A tool-calling agent:

1. `list_contract_clauses`: splits the contract into clauses (numbered headings, falling back to paragraphs)
2. `search_policies`: searches only the policy documents for each clause's obligations
3. `record_finding`: records `compliant`, `non_compliant` or `needs_review` with a reason and policy citations
4. `finish_review`: writes the summary once every clause has a finding

Guardrails: arguments are validated with Pydantic and errors are returned to the model so it can correct itself; unknown tools, unknown clause ids and citations to sources it never retrieved are rejected; `non_compliant` requires a citation; the loop is capped by `MAX_AGENT_STEPS` and `AGENT_TIMEOUT_SECONDS`, and any clause left without a finding is marked `needs_review` with an explanation. Overall risk is `high` if any clause is non-compliant, `medium` if any needs review, otherwise `low`. Works with OpenAI, Claude and Gemini; the Fake provider runs an offline demo agent.

Demo data (fictional, with five deliberate problems in the contract):

```bash
cd backend && .venv/bin/python -m app.scripts.make_sample_data   # writes ../sample_data/*.pdf
curl -F "file=@../sample_data/sample_internal_kyc_data_policy.pdf" -F "doc_type=policy" http://localhost:8000/documents
curl -F "file=@../sample_data/sample_vendor_kyc_agreement.pdf" -F "doc_type=contract" http://localhost:8000/documents
```

### Ingest documents

Embeddings use OpenAI by default (`OPENAI_API_KEY`); set `EMBEDDING_PROVIDER=fake` to run fully offline.

```bash
# Upload one PDF over HTTP (doc_type: policy | contract)
curl -F "file=@sample_data/rbi_kyc.pdf" -F "doc_type=policy" http://localhost:8000/documents

# Or ingest a whole folder from the host (skips files already ingested; --force to redo)
cd backend && .venv/bin/python -m app.scripts.ingest_folder ../sample_data
```

PDFs are split per page into ~500-token chunks with 80-token overlap (configurable via `CHUNK_SIZE_TOKENS` / `CHUNK_OVERLAP_TOKENS`), so every chunk carries exactly one page number for citations.

### Ask questions (RAG chat)

`provider` is one of `openai`, `anthropic`, `gemini` or `fake` (offline, no key needed); model names come from `OPENAI_CHAT_MODEL`, `ANTHROPIC_CHAT_MODEL` and `GEMINI_CHAT_MODEL`.

```bash
# Streamed answer as Server-Sent Events: token* -> citations -> done
curl -N -X POST http://localhost:8000/chat/stream -H 'content-type: application/json' \
  -d '{"question": "What documents are valid as proof of address under KYC rules?", "provider": "anthropic"}'

# Same, non-streaming (returns answer, citations, retrieved sources and token usage)
curl -X POST http://localhost:8000/chat -H 'content-type: application/json' \
  -d '{"question": "...", "provider": "openai", "conversation_id": "optional-id-for-follow-ups"}'
```

Answers cite sources inline as `[1]`, `[2]`; each citation maps to a document title, page number and snippet. If nothing relevant is retrieved, the API answers "I couldn't find this in the uploaded documents." without calling the model.

### Backend tests

Tests use fake embeddings and a fake LLM, so no API keys are needed. Database tests run against a `policypilot_test` database on the compose Postgres and are skipped if it is not running.

```bash
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

### Frontend checks

```bash
cd frontend
npm install
npm run lint && npm run typecheck && npm test   # ESLint, tsc, Vitest + Testing Library
```

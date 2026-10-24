# PolicyPilot — project memory

PolicyPilot is a portfolio project for an AI Application Engineer (LLM / Full-Stack) internship. Build it like a small production B2B product: clean code, tests, typed interfaces, clear README.

## Product
PolicyPilot is an AI compliance copilot for B2B teams (compliance, ops, legal).
- Users upload policy and regulatory PDFs (e.g., RBI KYC Master Direction, internal SOPs).
- Users ask questions in plain language and get streamed answers with page-level citations (document name + page number), using RAG.
- Users can switch the LLM provider per request: OpenAI, Anthropic Claude, or Google Gemini.
- "Contract Review" agent: user uploads a contract or document; a tool-calling agent checks its clauses against the stored policies and returns a structured compliance checklist (compliant / non-compliant / needs review, with reasons and policy citations).
- Admin page shows usage: requests, tokens, latency, estimated cost per provider.

## Tech stack (do not change without asking the user)
- Backend: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) + Alembic, uvicorn
- Vector store: PostgreSQL 16 with the pgvector extension
- Logs and chat history: MongoDB (motor async driver)
- LLM SDKs: openai, anthropic, google-genai
- Embeddings: one configurable embedding provider (default OpenAI embeddings); model name and dimension come from env vars
- PDF parsing: pypdf (keep page numbers for every chunk)
- Frontend: Next.js (App Router) + TypeScript + Tailwind CSS
- Testing: pytest + pytest-asyncio + httpx for the backend; ESLint + tsc type-check for the frontend
- Infra: Docker, Docker Compose, GitHub Actions, deployment to Google Cloud Run

## Repo structure
```
policypilot/
  backend/
    app/
      main.py
      core/        (config, logging, db sessions)
      api/         (routers: health, documents, chat, review, admin)
      models/      (SQLAlchemy models)
      schemas/     (Pydantic schemas)
      services/    (ingestion, retrieval, chat, agent, usage logging)
      llm/         (provider abstraction + openai/anthropic/gemini/fake providers)
    alembic/
    tests/
    Dockerfile
    pyproject.toml
  frontend/        (Next.js app)
  eval/            (evaluation script + test set)
  sample_data/     (PDFs, gitignored except a README)
  docs/            (architecture diagram, screenshots)
  docker-compose.yml
  .env.example
  .github/workflows/
  CLAUDE.md
  README.md
```

## Rules for every phase
- Model names, API keys, DB URLs: always from environment variables via the Settings class (`backend/app/core/config.py`). Never hardcode secrets or model names.
- All LLM calls go through the provider abstraction in `app/llm/` — no direct SDK calls elsewhere.
- Include a FakeProvider (deterministic, no network) so all tests run without API keys.
- Type hints everywhere; small functions; meaningful error messages and HTTP status codes.
- After each phase: run the tests, fix failures, then give (1) a summary of what was built, (2) how to run and verify it manually, (3) a suggested git branch name and commit message. Then STOP and wait for the next prompt. Do not start the next phase on your own.

## Phases
0. Scaffolding + local setup (docker compose, /health, Alembic with `vector` extension, Next.js layout) — done
1. Document ingestion (PDF → page-aware chunks → embeddings → pgvector) — done
2. RAG chat with citations, SSE streaming, multi-provider LLM layer — done
3. Next.js frontend (Chat + Documents) — done
4. Contract Review agent (tool calling) — done
5. MongoDB logging, conversation history, Admin dashboard — done
6. Testing, CI, RAG evaluation
7. Cloud Run deploy, README, demo polish

## Dev commands
- Everything: `docker compose up --build` (backend :8000, frontend :3000, postgres :5432, mongo :27017)
- Backend tests (no DB needed): `cd backend && pytest`
- Migrations: `cd backend && alembic upgrade head` (the backend container runs this on start)
- Frontend checks: `cd frontend && npm run lint && npm run typecheck && npm test` (Vitest 3.x: Node 20 is installed locally)
- After adding npm deps: `docker compose up -d --build -V frontend` (node_modules is an anonymous volume)

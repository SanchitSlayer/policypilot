# PolicyPilot developer commands. Everything runs inside the docker compose services,
# so a fresh clone only needs Docker and make.

COMPOSE   ?= docker compose
BACKEND   := $(COMPOSE) exec -T backend
FRONTEND  := $(COMPOSE) exec -T frontend
PROVIDERS ?= fake
TEST_DB_ENV := -e TEST_DATABASE_URL=postgresql+asyncpg://policypilot:policypilot@postgres:5432/policypilot_test \
               -e TEST_MONGO_URL=mongodb://mongo:27017 -e REQUIRE_TEST_DBS=1

.DEFAULT_GOAL := help
.PHONY: help up down logs migrate seed test test-backend test-frontend lint format eval

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  make %-14s %s\n", $$1, $$2}'

up: ## Build and start Postgres, MongoDB, the API and the web app
	$(COMPOSE) up -d --build --renew-anon-volumes
	@echo "Web app: http://localhost:3000   API docs: http://localhost:8000/docs"

down: ## Stop all services (data volumes are kept)
	$(COMPOSE) down

logs: ## Follow API and web app logs
	$(COMPOSE) logs -f backend frontend

migrate: ## Apply database migrations
	$(BACKEND) alembic upgrade head

seed: ## Load the demo policies and contract (add FORCE=1 to re-ingest)
	$(BACKEND) python -m app.scripts.seed $(if $(FORCE),--force)

test: test-backend test-frontend ## Run all tests

test-backend: ## Backend tests with coverage (pytest)
	$(COMPOSE) exec -T $(TEST_DB_ENV) backend pytest --cov --cov-report=term

test-frontend: ## Frontend unit tests (Vitest)
	$(FRONTEND) npm test

lint: ## Ruff lint + format check, ESLint, TypeScript type-check
	$(BACKEND) ruff check .
	$(BACKEND) ruff format --check .
	$(BACKEND) ruff check --config pyproject.toml /eval
	$(FRONTEND) npm run lint
	$(FRONTEND) npm run typecheck

format: ## Auto-format and auto-fix the backend and eval code
	$(BACKEND) ruff format . /eval
	$(BACKEND) ruff check --fix . /eval

eval: ## RAG evaluation, e.g. make eval PROVIDERS="openai anthropic gemini"
	$(BACKEND) python /eval/run_eval.py --providers $(PROVIDERS)

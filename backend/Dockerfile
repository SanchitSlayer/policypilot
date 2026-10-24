# syntax=docker/dockerfile:1
# Targets:
#   dev  - hot-reload image used by docker-compose (code is bind-mounted)
#   prod - default: small, non-root runtime image for Cloud Run (no dev tools, no compiler)

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------- dev
FROM python:${PYTHON_VERSION}-slim AS dev
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install -e ".[dev]"
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]

# ---------------------------------------------------------------- build
FROM python:${PYTHON_VERSION}-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
# Install dependencies first so code changes do not invalidate this layer.
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install . && pip uninstall -y policypilot-backend
# Bake the tokenizer file in, so containers never download it at startup.
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

# ---------------------------------------------------------------- prod
FROM python:${PYTHON_VERSION}-slim AS prod
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken \
    ENVIRONMENT=production \
    PORT=8080 \
    WEB_CONCURRENCY=2
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/tiktoken /opt/tiktoken
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app config ./config
COPY --chown=app:app app ./app
USER app
EXPOSE 8080
# Cloud Run sends traffic through its proxy: trust X-Forwarded-* so client IPs (rate limits)
# and the HTTPS scheme are correct. No access log: Cloud Run already logs requests, and client
# IPs are personal data. Migrations run as a separate job, not on every start.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\" --workers \"$WEB_CONCURRENCY\" --proxy-headers --forwarded-allow-ips='*' --no-server-header --no-access-log"]

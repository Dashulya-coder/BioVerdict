# syntax=docker/dockerfile:1
# Build from the repository root: docker build -f backend/Dockerfile .
FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
WORKDIR /app

# Cache dependencies separately from application code; keep the existing lockfile.
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY backend/README.md ./README.md
COPY backend/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    FIXTURES_DIR=/app/fixtures \
    DB_PATH=/app/data/bioverdict.sqlite \
    CACHE_DIR=/app/data/cache \
    USE_FIXTURES=1
WORKDIR /app

RUN groupadd --gid 10001 bioverdict \
    && useradd --uid 10001 --gid bioverdict --no-log-init --no-create-home bioverdict \
    && mkdir -p /app/data/cache \
    && chown -R bioverdict:bioverdict /app/data

COPY --from=builder /app/.venv /app/.venv
COPY fixtures/bundles ./fixtures/bundles
COPY fixtures/resolver ./fixtures/resolver
COPY fixtures/reasoning ./fixtures/reasoning

USER bioverdict
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

# Runs and their background tasks currently live in one API process.
CMD ["uvicorn", "bioverdict.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

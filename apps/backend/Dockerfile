# ===================== Requirements Export Stage =====================
# Export requirements from uv.lock for reproducible, secure builds.
# Build context is apps/backend (its own pyproject + uv.lock; there is no uv
# workspace root): docker build -f apps/backend/Dockerfile --target prod apps/backend
FROM python:3.11-slim AS requirements-prod

WORKDIR /tmp

# Use official uv image with pinned version for reproducibility
COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./

# Export from lock file (not re-resolving dependencies!); --no-emit-workspace
# keeps only external dependencies, --frozen fails loudly on a stale lock
RUN uv export --frozen --no-dev \
    --no-emit-workspace --no-editable -o requirements.txt

# Dev requirements = prod + the `dev` extra (ruff, mypy, pytest, ...). A stage of its
# own, so a --target prod build never pays for an export only `dev` consumes.
FROM requirements-prod AS requirements-dev

RUN uv export --frozen --extra dev \
    --no-emit-workspace --no-editable -o requirements.txt

# ===================== Production Base Stage =====================
FROM python:3.11-slim AS base

WORKDIR /app

# uv is mounted for the install and never lands in a layer — 20MB of build tooling
# in a runtime image is attack surface paid for on every pull. Every dependency
# resolves to a manylinux wheel, so no compiler is installed here either.
COPY --from=requirements-prod /tmp/requirements.txt .
RUN --mount=from=ghcr.io/astral-sh/uv:0.9.9,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt && \
    rm requirements.txt

# The runtime image is also the immutable migration artifact used by CD.
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini .

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Every stage runs unprivileged. Created once here so the uid is identical across
# them; each stage still chowns after its own COPYs.
RUN groupadd -r appuser && useradd -r -m -g appuser appuser

# ===================== Development Stage =====================
FROM base AS dev

WORKDIR /app/src

COPY --from=requirements-dev /tmp/requirements.txt .
RUN --mount=from=ghcr.io/astral-sh/uv:0.9.9,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt && \
    rm requirements.txt

# Copy test files for development
COPY tests ./tests

RUN chown -R appuser:appuser /app
USER appuser

# Development command with FastAPI CLI auto-reload
CMD ["fastapi", "dev", "interfaces/main.py", "--host", "0.0.0.0", "--port", "8000"]

# ===================== Migration Stage =====================
# Optional one-shot target for local Compose and other Docker-based deployments.
FROM base AS migrate

# Optional build arg for CI/CD pipelines
ARG DATABASE_URL=""

RUN chown -R appuser:appuser /app
USER appuser

# Set build-time DATABASE_URL as environment variable if provided
ENV DATABASE_URL=${DATABASE_URL}

# Default command runs migrations
CMD ["alembic", "upgrade", "head"]

# ===================== Production Stage =====================
FROM base AS prod

WORKDIR /app/src

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# One process: sessions, OAuth login state and login rate-limit counters live in its memory.
CMD ["fastapi", "run", "interfaces/main.py", "--host", "0.0.0.0", "--port", "8000"]

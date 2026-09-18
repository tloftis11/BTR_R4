# ─── Stage 1: Build React frontend ─────────────────────────────────────────
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

RUN npm install -g pnpm

# PNPM_CONFIG_MINIMUM_RELEASE_AGE=0: defensive belt-and-suspenders alongside
# frontend/pnpm-workspace.yaml's minimumReleaseAge:0 -- the env var is the
# only form honored across pnpm's CLI flag inconsistencies (a --config.* CLI
# flag is silently ignored on pnpm 12's Rust CLI). See pnpm-workspace.yaml
# for why this check is disabled at all.
ENV PNPM_CONFIG_MINIMUM_RELEASE_AGE=0

COPY frontend/package.json frontend/pnpm-lock.yaml* frontend/pnpm-workspace.yaml* ./
RUN pnpm install --frozen-lockfile

COPY frontend/ .
# Empty VITE_API_URL = same-origin (FastAPI serves the frontend in production)
RUN VITE_API_URL="" pnpm build

# ─── Stage 2: Production runtime ────────────────────────────────────────────
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1

# Install uv
RUN pip install --no-cache-dir uv

# Install Python deps first (layer-cached until pyproject.toml changes).
WORKDIR /app/backend
COPY backend/pyproject.toml .
RUN uv sync --no-dev

# Copy backend source
COPY backend/ .

# Copy static geo reference files (us-states.json etc.) that ship in git.
WORKDIR /app
COPY data/ ./data/

# Build the DuckDB file fresh at image-build time: seed the static reference
# dimensions, then run all 4 ETLs against their live public APIs. Unlike
# measles-hotspot's one-time synthetic seed (committed to git and copied in),
# this data is meant to be re-pulled on every deploy, not baked in once --
# see backend/db.py and .dockerignore for why data/*.duckdb is never
# committed. This does mean: (a) a deploy fails if a source API is down or a
# schema changes underneath us -- same "verify, don't assume" risk we hit
# repeatedly building the ETLs locally, now happening at build time instead
# of dev time; (b) build times are meaningfully longer (~100K+ rows pulled
# and paginated across 5 live APIs).
WORKDIR /app/backend
RUN uv run python -m seed.seed_sources && \
    uv run python -m seed.seed_pathogens && \
    uv run python -m seed.seed_geo && \
    uv run python -m etl.wastewater --weeks 12 && \
    uv run python -m etl.syndromic --weeks 12 && \
    uv run python -m etl.genomic --weeks 26 && \
    uv run python -m etl.travel --weeks 26

# Copy React build output — FastAPI serves it via StaticFiles
COPY --from=frontend-builder /app/frontend/dist /app/static/

EXPOSE 8000

WORKDIR /app/backend
# Render injects $PORT; fall back to 8000 for local docker run
CMD ["sh", "-c", "uv run uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]

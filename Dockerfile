# DocRunr — document processing worker
# Usage:
#   docker build -t docrunr .
#   docker run docrunr

# Stage 1: UI build
FROM node:25-bookworm-slim AS ui-builder

WORKDIR /app

RUN corepack enable

# Semantic version without leading "v" (matches release tag); CI sets this from GITHUB_REF_NAME
ARG DOCRUNR_VERSION=
ENV VITE_APP_VERSION=${DOCRUNR_VERSION}

# Install UI dependencies with lockfile
COPY ui/package.json ui/pnpm-lock.yaml ./ui/
RUN pnpm -C ui install --frozen-lockfile

# Build production UI assets
COPY ui/ ./ui/
RUN pnpm -C ui build

# Stage 2: Python builder
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy workspace root (lockfile + workspace definition)
COPY pyproject.toml uv.lock ./

# Install core dependencies first (cache layer)
COPY core/pyproject.toml ./core/
COPY worker/pyproject.toml ./worker/
RUN uv sync --frozen --no-dev --no-install-workspace

# Copy source and install all workspace packages
COPY core/src/ ./core/src/
COPY worker/src/ ./worker/src/
RUN uv sync --frozen --no-dev

# Stage 3: Runtime
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="DocRunr"
LABEL org.opencontainers.image.description="Document to clean Markdown and chunks"
LABEL org.opencontainers.image.source="https://github.com/docrunr/docrunr"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Minimal runtime fonts used by extraction engines
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation \
    fonts-dejavu-core \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Non-root user
RUN groupadd --gid 1000 docrunr \
    && useradd --uid 1000 --gid docrunr --shell /bin/bash --create-home docrunr

WORKDIR /app

# Copy virtual environment and source from builder
COPY --from=builder --chown=docrunr:docrunr /app/.venv /app/.venv
COPY --from=builder --chown=docrunr:docrunr /app/core/src /app/core/src
COPY --from=builder --chown=docrunr:docrunr /app/worker/src /app/worker/src
COPY --from=ui-builder --chown=docrunr:docrunr /app/ui/dist /app/worker/src/docrunr_worker/ui_dist

# Shared data and cache directories
ENV HF_HOME=/app/.cache/huggingface
ENV TIKTOKEN_CACHE_DIR=/app/.cache/tiktoken

RUN mkdir -p /data/input /data/output /db /app/.cache/huggingface /app/.cache/tiktoken \
    && chown -R docrunr:docrunr /data /db /app/.cache

# Workspace venv on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HEALTH_PORT=8080

USER docrunr

# Pre-download ML models and tokenizer data at build time
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); print('tiktoken: ok')"
RUN python -c "from magika import Magika; Magika(); print('magika: ok')"
RUN python -c "from docling.document_converter import DocumentConverter; DocumentConverter(); print('docling: ok')"

# Enforce offline mode after model download
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

# Smoke-test
RUN python -c "import docrunr_worker; print('DocRunr loaded')"

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; p=os.environ.get('HEALTH_PORT', '8080'); urllib.request.urlopen(f'http://localhost:{p}/health')" || exit 1

EXPOSE 8080

ENTRYPOINT ["docrunr-worker"]

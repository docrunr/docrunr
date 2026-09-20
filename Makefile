.DEFAULT_GOAL := help

.PHONY: help install dev api-dev purge lint fallow skylos test test-api test-samples \
	test-integration-txt test-integration-s3 test-integration-llm test-integration-api \
	download-samples docker-run docker-build release

FILTER ?= *
INCLUDE ?= *
SOURCE ?= samples
COUNT ?= 5
MIME ?= pdf
N ?= 5
PROFILE ?= local
TARGET ?= all
VERSION ?=

help:
	@echo "  make install                 uv sync + UI deps"
	@echo "  make dev                     start full local stack (workers, API, UI, LiteLLM)"
	@echo "  make api-dev                 public API with reload on :8082"
	@echo "  make purge                   stop Compose, remove DocRunr volumes and caches"
	@echo "  make lint                    Python + UI lint/format/typecheck"
	@echo "  make fallow                  UI dead-code audit"
	@echo "  make skylos                  static analysis"
	@echo "  make test                    unit tests (FILTER=name, default all)"
	@echo "  make test-api                runtime + public API unit tests"
	@echo "  make test-samples            run pipeline on tests/samples (INCLUDE=glob)"
	@echo "  make test-integration-txt    integration TXT (SOURCE=samples|downloads COUNT=n)"
	@echo "  make test-integration-s3     integration S3"
	@echo "  make test-integration-llm    integration LLM"
	@echo "  make test-integration-api    integration public API"
	@echo "  make download-samples        fetch sample docs (MIME=pdf N=5)"
	@echo "  make docker-run              compose up (PROFILE=local|s3)"
	@echo "  make docker-build            build images (TARGET=all|txt|llm|api)"
	@echo "  make release                 tag and push (VERSION=X.Y.Z, or empty for patch bump)"

install:
	uv sync
	pnpm -C ui install

dev:
	node ./scripts/dev.mjs

api-dev:
	mkdir -p "$(CURDIR)/.data"
	RABBITMQ_HOST=localhost \
	STORAGE_BASE_PATH="$(CURDIR)/.data" \
	API_DB_PATH="$(CURDIR)/.data/docrunr-api.sqlite" \
	LITELLM_BASE_URL=http://localhost:4000 \
	uv run uvicorn docrunr_api.app:create_app --factory --reload --host 127.0.0.1 --port 8082

purge:
	./scripts/purge.sh

lint:
	node ./scripts/lint.mjs

fallow:
	pnpm -C ui exec fallow dead-code

skylos:
	uv run skylos .

test:
	node ./scripts/test.mjs unit "$(FILTER)"

test-api:
	uv run pytest -q tests/runtime tests/api

test-samples:
	node ./scripts/test.mjs samples "$(INCLUDE)"

test-integration-txt:
	node ./scripts/test.mjs integration txt "$(SOURCE)" "$(COUNT)"

test-integration-s3:
	node ./scripts/test.mjs integration s3 "$(SOURCE)" "$(COUNT)"

test-integration-llm:
	node ./scripts/test.mjs integration llm "$(SOURCE)" "$(COUNT)"

test-integration-api:
	node ./scripts/test.mjs integration api

download-samples:
	uv run python -m tests.downloads "$(MIME)" "$(N)"

docker-run:
	node ./scripts/docker.mjs run "$(PROFILE)"

docker-build:
	node ./scripts/docker.mjs build "$(TARGET)"

release:
ifeq ($(strip $(VERSION)),)
	printf '\n' | ./scripts/release.sh --push
else
	./scripts/release.sh --version "$(VERSION)" --push
endif

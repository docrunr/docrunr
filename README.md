<p align="center">
  <img src="./ui/src/assets/logo-black.svg#gh-light-mode-only" alt="DocRunr" width="80" />
  <img src="./ui/src/assets/logo-white.svg#gh-dark-mode-only" alt="DocRunr" width="80" />
</p>

<h1 align="center">DocRunr</h1>
<h3 align="center">Document to clean Markdown and chunks. That's it.</h3>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue" alt="License: Apache-2.0" /></a>
  <a href="https://github.com/docrunr/docrunr/issues"><img src="https://img.shields.io/badge/Contributions-welcome-brightgreen.svg" alt="Contributions welcome" /></a>
  <img src="https://img.shields.io/badge/Python-3.11+-3776ab?logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/Queue-RabbitMQ-ff6600?logo=rabbitmq&logoColor=white" alt="RabbitMQ" />
</p>

<p align="center">
  <img src="./assets/docrunr-intro.gif" alt="DocRunr dashboard: metrics, activity heatmap, and charts" />
</p>

DocRunr gives you two ways to run document processing: a CLI for local and batch work, and a Docker container with a UI for your RAG stack development and production deployments.

### ✨ **Highlights**

- Binary file detection.
- Clean Markdown and stable chunk JSON output.
- Automatic parser fallback when extraction quality is weak.
- Worker setup with queue processing, uploads, health, stats, and artifact inspection.
- UI for uploads, jobs, and output review.

### 🎯 **Simple by design**

DocRunr does one job: it turns messy documents into clean Markdown and structured chunks. PDFs, Office files, email, HTML, images with text.

DocRunr is built for general purpose document handling, not for every possible document edge case. The goal is to make the common 80% of real world documents usable with a predictable pipeline, not to promise perfect conversion for every domain specific layout, template, or special use case. There will always be documents and use cases that need custom handling outside DocRunr.

Chunks are simple by design. We lean on the structure already in the document and use one chunking approach only: recursive, structure-based splitting with no overlap. Headings come first, paragraphs come next, and sentence boundaries are only used when needed. No strategy matrix, no tuning exercise, no guessing which splitter to use. The behavior is stable, documented in [`SPEC.md`](./SPEC.md), and easy to rely on in production. DocRunr solves this one part of your stack so you can stop thinking about document extraction and chunking and move on to the rest.

### 🔄 **How it works**

DocRunr fits into one small part of your stack. Locally, you can run the CLI on files directly. In Docker or production, you push jobs to RabbitMQ and let the DocRunr worker do the extraction and chunking.

```mermaid
flowchart LR
    A[Documents] --> B[RabbitMQ]
    B --> C[DocRunr]
    C --> B
    C --> D["📝 Clean Markdown (.md)"]
    C --> E["🧩 Structured chunks (.json)"]
```

The bundled UI sits on top of that same flow. It gives you an easy way to upload documents, inspect jobs, and review artifacts without building your own operator tooling first.

### 🐳 **Docker**

The default Docker stack is RabbitMQ, the TXT worker, the LLM worker (LiteLLM + in-Docker Ollama), and local storage under `./.data`:

```bash
docker compose up -d --build
```

Open **http://localhost:8080** for the TXT extraction dashboard (upload, jobs, artifacts). Open **http://localhost:8081** for the LLM worker dashboard (host port only; inside Docker both workers listen on **8080**, with **8081→8080** published for `worker-llm`). Each worker serves `/health`, `/stats`, and `/api/*` on its host URL.

If the TXT container fails to start with “bind: address already in use” on **8080**, another process on your machine is using that port—stop it or change **`HEALTH_PORT`** in `.env` and the compose port mapping for `worker`.

**Object storage:** Use the MinIO overlay so both workers use S3-compatible storage (MinIO must be last so it overrides `STORAGE_TYPE`):

```bash
docker compose -f docker-compose.base.yml -f docker-compose.llm.yml -f docker-compose.ollama.yml -f docker-compose.minio.yml up -d --build
```

**LLM embeddings:** Pass `llm_profile` on extraction jobs to trigger a follow-up embedding step. See [`SPEC.md`](./SPEC.md) (section 20) for the full protocol. With **docker-compose.ollama.yml**, the Ollama container runs **`scripts/ollama-docker-entrypoint.sh`**, which **`ollama pull`s** each configured model before **`exec ollama serve`**. Set **`OLLAMA_EMBED_MODELS`** to a comma-separated list (e.g. `nomic-embed-text,embeddinggemma,bge-m3`). The default pulls all four models configured in `litellm.yaml`.

```bash
# Dev mode (host Ollama via brew; TXT on 8080, worker-llm on 8081):
node ./scripts/dev.mjs --llm
```

<details>
<summary>Queue payloads</summary>

**Extraction**

Job (`docrunr.jobs`): `job_id`, `source_path` required; optional `filename`, `options`, `priority` (0–255), `llm_profile` (LiteLLM `model_name`; when non-empty and extraction succeeds, the worker publishes a follow-up to `docrunr.llm.jobs`). Declare the queue with priority (e.g. `x-max-priority: 255`) and set AMQP `priority` to match.

Result (`docrunr.results`): `status` `ok` or `error`; `markdown_path` / `chunks_path` or `error`; echoes `priority` and `llm_profile`.

```json
{
  "job_id": "…",
  "filename": "report.pdf",
  "source_path": "input/…/….pdf",
  "options": {},
  "priority": 0,
  "llm_profile": "nomic-embed-text-137m"
}
```

```json
{
  "job_id": "…",
  "status": "ok",
  "filename": "report.pdf",
  "source_path": "input/…/….pdf",
  "markdown_path": "output/…/….md",
  "chunks_path": "output/…/….json",
  "total_tokens": 0,
  "chunk_count": 0,
  "duration_seconds": 0,
  "error": null,
  "priority": 0,
  "llm_profile": "nomic-embed-text-137m"
}
```

**LLM** (optional `worker-llm`; see [`SPEC.md`](./SPEC.md), section 20)

After a successful extraction with `llm_profile` set, the TXT worker publishes to `docrunr.llm.jobs`. `worker-llm` consumes that queue and publishes outcomes to `docrunr.llm.results` (failures that exhaust retries go to `docrunr.llm.dlq`, same pattern as extraction).

LLM job (`docrunr.llm.jobs`): `job_id`, `extract_job_id`, `filename`, `source_path`, `chunks_path`, `llm_profile` required for normal processing; optional `priority`, `metadata` (object).

```json
{
  "job_id": "new-uuid",
  "extract_job_id": "original-extraction-uuid",
  "filename": "report.pdf",
  "source_path": "input/2026/04/15/00/original-uuid.pdf",
  "chunks_path": "output/2026/04/15/00/original-uuid.json",
  "llm_profile": "nomic-embed-text-137m",
  "priority": 0,
  "metadata": {}
}
```

LLM result (`docrunr.llm.results`): `status` `ok` or `error`; on success, `artifact_path` points at the embeddings JSON; `provider`, `chunk_count`, `vector_count`, and `duration_seconds` describe the run.

```json
{
  "job_id": "new-uuid",
  "extract_job_id": "original-extraction-uuid",
  "status": "ok",
  "filename": "report.pdf",
  "source_path": "input/…/….pdf",
  "chunks_path": "output/…/….json",
  "llm_profile": "nomic-embed-text-137m",
  "provider": "ollama",
  "chunk_count": 12,
  "vector_count": 12,
  "duration_seconds": 3.41,
  "artifact_path": "output/…/….embeddings.json",
  "error": null
}
```

</details>

**Environment variables:** Text extraction and LLM workers are configured only via env vars; tables and defaults are in [`SPEC.md`](./SPEC.md) (section 22, *Configuration*, and section 20 for the LLM worker).

### 🛠 **Tech stack**

- **Core runtime:** Python
- **Queue:** RabbitMQ
- **UI:** React, Vite, Mantine
- **Storage:** local disk or MinIO
- **Packaging:** Docker

### 💻 **Development**

To work on DocRunr locally, you need Python 3.11+, [`uv`](https://github.com/astral-sh/uv), Node.js 20+ with `corepack` for `pnpm`, and Docker for the local stack and integration tests.

```bash
git clone https://github.com/docrunr/docrunr.git
cd docrunr
cp .env.example .env
uv sync
pnpm -C ui install
```

**Workspace layout**

```
docrunr/
├── core/           # docrunr on PyPI (CLI + library)
├── worker/         # docrunr-worker (RabbitMQ, HTTP, bundled UI assets)
├── worker-llm/     # docrunr-worker-llm (optional LLM post-processing)
├── ui/             # React + Mantine; Vite in dev, static bundle in the image
├── tests/          # core, worker, worker_llm, integration, samples
└── scripts/        # release and dev helpers
```

#### Commands

After the clone and `.env` copy above, the commands below install dependencies and run DocRunr Worker in dev mode. For Docker, tests, lint, release, and other workflows, use the tasks in [`.vscode/tasks.json`](./.vscode/tasks.json).

| Command                  | Description                                        |
| ------------------------ | -------------------------------------------------- |
| `uv sync`                | Install the Python workspace and dev dependencies. |
| `pnpm -C ui install`     | Install UI dependencies.                           |
| `node ./scripts/dev.mjs` | Start dev                                          |
| `node ./scripts/dev.mjs --llm` | Start dev with LLM worker + LiteLLM        |

### ⌨️ **CLI**

The `docrunr` command processes a single file or walks a directory of supported documents and writes cleaned Markdown (`.md`) and chunk metadata (`.json`) next to each input unless you set `--out`. It uses the same pipeline as `convert()` in Python—no config files, same predictable output for the same input. The options table covers output location, verbose extraction logs, batch summary JSON, parallel workers, and filename filters. Full behavior, exit codes, and JSON shapes are documented in [`SPEC.md`](./SPEC.md).

Install from PyPI:

```bash
uv pip install docrunr
```

```bash
docrunr document.pdf
docrunr ./documents/ --out ./output -v -r
```

```python
from docrunr import convert

result = convert("report.pdf")
result.markdown
result.chunks
```

| Option      | Short | Description                              |
| ----------- | ----- | ---------------------------------------- |
| `--out`     | `-o`  | Output directory (default: beside input) |
| `--verbose` | `-v`  | Extraction details and timing            |
| `--report`  | `-r`  | Batch report JSON                        |
| `--workers` | `-w`  | Parallel workers for batch (`0` = auto)  |
| `--include` | `-i`  | Filter by name, extension, or glob       |

### 📋 **Supported formats**

DocRunr picks a parser from the file’s **detected MIME type** (binary based, via [Magika](https://github.com/google/magika)), not from the filename alone. Today the built-in registry handles the MIME types listed below, which correspond to the extensions in the table.

| Category      | Formats                       |
| ------------- | ----------------------------- |
| Documents     | PDF, DOCX, DOC, ODT           |
| Spreadsheets  | XLSX, XLS, ODS, CSV           |
| Presentations | PPTX, PPT, ODP                |
| Email         | EML, MSG                      |
| Web & markup  | HTML, HTM, XML, MD, JSON, TXT |
| Images        | JPG, JPEG, PNG, TIFF, BMP     |

### 📄 **License**

DocRunr is licensed under the **Apache License 2.0**.

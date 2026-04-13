# DocRunr Specification

**You give it a document. It gives you clean Markdown and chunks. That's it.**

---

## 1. What DocRunr Is

DocRunr is a predictable document processing toolkit that converts documents into clean Markdown and structured text chunks ready for RAG pipelines. It works as a CLI, a Python library, and a scalable RabbitMQ worker with a bundled UI.

It detects the file type, picks the best extraction strategy, cleans the Markdown, and splits it into structure-aware chunks. Zero configuration. No tuning. No knobs. It just works.

```
docrunr report.pdf  →  report.md + report.json
```

---

## 2. What DocRunr Is Not

- A configurable pipeline framework
- An embedding engine or vector store
- An LLM-powered extraction tool
- A document editor or management system

Core document extraction is local. No hosted APIs. No telemetry. No LLM calls. Just solid engineering around document conversion and chunking.

---

## 3. Design Principles

**Simplicity.** One command. Minimal interface. The tool is smart so the user doesn't have to be.

**Predictability.** Same input, same output. Always.

**Reliability.** Extraction recovers automatically from failures. The user never sees a fallback — they see clean output.

**Opinionated defaults.** No tuning dials. The defaults are the right answer.

**Composability.** Output is plain Markdown and JSON. Pipe it anywhere.

---

## 4. Guarantees

These are promises DocRunr makes. They do not change without a major version bump.

1. **Identical inputs always produce identical outputs.**
2. **One bad file never crashes a batch.**
3. **Core extraction is local.** No hosted APIs or telemetry are involved in document conversion. The worker may still talk to configured infrastructure such as RabbitMQ or MinIO.
4. **Extraction fallbacks are automatic.** Parser failures do not expose stack traces in normal user flows; if every parser fails, the file is reported as failed.
5. **Output is always valid UTF-8 Markdown.**
6. **JSON schema is stable.** Downstream consumers can rely on the shape.

---

## 5. Supported Formats

DocRunr supports every file type that its extraction engines can handle. The full list:

| Category     | Formats                                           |
| ------------ | ------------------------------------------------- |
| PDF          | `.pdf`                                            |
| Office       | `.docx`, `.doc`, `.pptx`, `.ppt`, `.xlsx`, `.xls` |
| OpenDocument | `.odt`, `.ods`, `.odp`                            |
| Web          | `.html`, `.htm`                                   |
| Text         | `.txt`, `.md`, `.csv`, `.json`, `.xml`            |
| Email        | `.eml`, `.msg`                                    |
| Images       | `.jpg`, `.jpeg`, `.png`, `.tiff`, `.bmp`          |

File type detection is content-based via Magika, not extension-based.

Unsupported files are skipped with a clear message.

---

## 6. CLI

### Usage

```
docrunr <input>
```

`<input>` is a file or a directory. That's the entire interface.

```
docrunr report.pdf
docrunr ./documents/
```

### Options

| Option      | Short | Description                                |
| ----------- | ----- | ------------------------------------------ |
| `--out`     | `-o`  | Output directory (default: next to input)  |
| `--verbose` | `-v`  | Show extraction details and timing         |
| `--report`  | `-r`  | Write a batch report JSON to output dir    |
| `--workers` | `-w`  | Parallel workers for batch (0 = auto/CPUs) |
| `--include` | `-i`  | Filter files by name, extension, or glob   |

When processing a directory, the output mirrors the input directory structure.

### Exit Codes

| Code | Meaning                     |
| ---- | --------------------------- |
| 0    | All files processed         |
| 1    | Some files failed           |
| 2    | Fatal error or bad argument |

---

## 7. Output

For each input document, DocRunr writes two files:

### Markdown

`<name>.md` — cleaned, normalized Markdown. This is the primary output.

### Chunks JSON

`<name>.json` — structured, retrieval-ready chunks.

```json
{
  "docrunr_version": "0.0.0",
  "source": "article.html",
  "content_hash": "sha256:5b31a8f2f0c4f8f4f17685c2b9b0fbb0f3cb2a4e4db31a9ed8097282b8e5e6f0",
  "mime_type": "text/html",
  "size_bytes": 824,
  "parser": "BeautifulSoupHtmlParser",
  "duration_seconds": 0.18,
  "total_tokens": 42,
  "content": "# Introduction\n\nDocRunr emits predictable chunks.\n\n## Methods\n\nChunking follows heading boundaries.\n\n## Conclusion\n\nOutput stays stable across runs.\n",
  "chunks": [
    {
      "chunk_index": 0,
      "text": "# Introduction\n\nDocRunr emits predictable chunks.",
      "section_path": ["Introduction"],
      "token_count": 14,
      "char_count": 50
    },
    {
      "chunk_index": 1,
      "text": "## Methods\n\nChunking follows heading boundaries.",
      "section_path": ["Introduction", "Methods"],
      "token_count": 13,
      "char_count": 46
    },
    {
      "chunk_index": 2,
      "text": "## Conclusion\n\nOutput stays stable across runs.",
      "section_path": ["Introduction", "Conclusion"],
      "token_count": 15,
      "char_count": 45
    }
  ]
}
```

The JSON schema is stable. Build on it.

Chunk object contract:

- `chunk_index`: zero-based, stable order in output
- `text`: chunk payload from cleaned Markdown
- `section_path`: ordered heading ancestry from top-level to deepest/current heading
- `token_count`: token count for `text`
- `char_count`: character count for `text`

`section_path` notes:

- Always present on every chunk.
- Chunks before the first heading use `[]`.
- The last element is the chunk's most specific local section.

### Batch Report

When `--report` is passed and processing a directory, DocRunr writes `_report.json`:

```json
{
  "total": 10,
  "succeeded": 9,
  "failed": 1,
  "duration_seconds": 12.4,
  "files": [
    { "file": "report.pdf", "status": "ok", "chunks": 12, "tokens": 4830 },
    { "file": "broken.docx", "status": "error", "error": "corrupt file" }
  ]
}
```

---

## 8. Processing Pipeline

```
Input file
  ↓
File type detection (Magika)
  ↓
Parser selection (registry lookup + fallback chain)
  ↓
Extraction (document → raw Markdown)
  ↓
Markdown cleaning (normalize whitespace, headers, tables, lists)
  ↓
Chunk generation (structure-based, paragraph-aware)
  ↓
Output (.md + .json)
```

Every stage is predictable. No randomness. No hosted APIs. Core extraction stays local.

---

## 9. Parser Registry

Parsers are registered via a decorator. Each parser declares which MIME types it handles and a priority. For each file type, DocRunr tries parsers in priority order until one produces acceptable output.

```python
@register_parser(mime_types=["application/pdf"], priority=10)
class DoclingPdfParser(BaseParser):
    def parse(self, path: Path) -> str:
        """Returns Markdown. Raises on failure."""
        ...
```

The parser contract is intentionally simple:

- **Input:** a file path
- **Output:** a Markdown string
- **Failure:** raise an exception

If a parser fails, the next one runs. If all fail, the file is recorded as failed. The user never picks a parser — the registry handles it.

---

## 10. Quality Gate

After each extraction attempt, DocRunr scores the output with fast heuristics:

- Minimum text length
- Printable character ratio
- Whitespace density
- Repeated content detection

If the score is below threshold, the next parser in the chain runs. If every parser scores below threshold, the best result is used. Something is always better than nothing.

---

## 11. Markdown Cleaning

Deterministic cleanup rules applied to every extraction:

- Whitespace normalization (collapse blank lines, strip trailing spaces)
- Header hierarchy repair (ensure proper nesting)
- Page number and header/footer removal
- List formatting normalization
- Table cleanup
- Unicode normalization

**Rule:** If a transformation changes _what information_ is present, it doesn't belong here. Cleaning changes _how_ information is formatted, not _what_ it says.

---

## 12. Chunk Generation

After cleaning, DocRunr splits content into retrieval-ready chunks.

**Strategy: structure-based, paragraph-aware.**

Chunks are split at structural boundaries in this order of preference:

1. Headings (each section becomes a chunk or set of chunks)
2. Paragraphs (natural break points within sections)
3. Sentence boundaries (only when a section exceeds token budget)

| Parameter         | Value      |
| ----------------- | ---------- |
| Target size       | 300 tokens |
| Hard max          | 450 tokens |
| Token counter     | tiktoken   |
| Recommended floor | 200 tokens |

No overlap. No sliding window. Structure-preserving splits only.

Token windows keep growing. Keeping chunks aligned to document structure is more valuable than optimizing for a specific window size. When a paragraph is short, it rolls into the next chunk. When a heading starts, a new chunk starts.

---

## 13. Dependencies

Dependencies are expected to use permissive licenses suitable for redistribution in this project (for example Apache 2.0, MIT, or BSD-style licenses).

### Core

| Library          | Purpose                        | License    |
| ---------------- | ------------------------------ | ---------- |
| `docling`        | Layout-aware document parsing  | MIT        |
| `markitdown`     | Office and web extraction      | MIT        |
| `kreuzberg`      | Legacy Office + ODT extraction | MIT        |
| `magika`         | Content-based type detection   | Apache 2.0 |
| `pypdfium2`      | Fast PDF text extraction       | Apache 2.0 |
| `tiktoken`       | Token counting                 | MIT        |
| `beautifulsoup4` | HTML parsing                   | MIT        |
| `typer`          | CLI framework                  | MIT        |
| `rich`           | Terminal output and progress   | MIT        |

### Worker

| Library             | Purpose                      | License    |
| ------------------- | ---------------------------- | ---------- |
| `pika`              | RabbitMQ client              | BSD        |
| `pydantic-settings` | Env-based configuration      | MIT        |
| `minio`             | S3-compatible storage (opt.) | Apache 2.0 |

**Package management:** uv

If a parser's dependency is not installed, that parser is skipped silently. No import errors. No crashes.

---

## 14. Logging

**Default:** quiet. One line per file processed.

**Verbose (`--verbose`):** parser attempts, quality scores, fallback decisions, timing, token counts.

Two modes. That's enough.

---

## 15. Error Handling

DocRunr handles gracefully:

- Corrupted documents
- Unsupported file types
- Parser library failures
- Empty content
- Permission errors

Failed files are skipped with a message. They never crash the batch.

---

## 16. Python API

```python
from docrunr import convert

result = convert("report.pdf")

result.markdown   # cleaned Markdown string
result.chunks     # list of Chunk objects
```

The API mirrors CLI behavior exactly. Same input, same output, same predictability.

---

## 17. Project Structure

The layout is **package- and directory-oriented**. Individual Python modules may be split, merged, or renamed as implementation evolves; what matters is where responsibilities live, not a fixed list of `.py` files.

```
docrunr/
├── pyproject.toml                 # uv workspace root (wires core + worker)
├── uv.lock
│
├── core/                          # CLI + library package (`docrunr` on PyPI paths)
│   ├── pyproject.toml
│   └── src/docrunr/               # Public API, CLI, pipeline (detect → parse → clean → chunk)
│       ├── parsers/               # Format parsers, registry, shared converter helpers
│       └── py.typed
│
├── worker/                        # RabbitMQ worker package (`docrunr_worker`)
│   ├── pyproject.toml
│   └── src/docrunr_worker/        # Consume jobs, call core, storage I/O, HTTP health/UI, job history
│
├── ui/                            # Vite + React front end (package name: docrunr-ui)
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── app/                   # Shell, layout, sections, routing glue
│       ├── features/              # Feature-oriented screens and flows
│       ├── components/            # Shared UI
│       ├── services/              # Worker / API client types and calls
│       ├── hooks/
│       ├── i18n/
│       ├── utils/
│       └── assets/                # Logos and other static assets
│
├── tests/
│   ├── core/                      # Unit tests for docrunr
│   ├── worker/                    # Unit tests for docrunr_worker
│   ├── integration/               # Opt-in tests (RabbitMQ, storage, upload E2E)
│   ├── downloads/                 # Runnable package to fetch sample fixtures
│   └── samples/                   # Test inputs (by format); some files fetched via downloads/
│
├── scripts/                       # dev.mjs, lint.mjs, release.sh, purge.sh
├── .github/workflows/             # ci.yml, release.yml
│
├── Dockerfile                     # Single image for CLI + worker
├── docker-compose.yml             # Includes base + local (default `docker compose up`)
├── docker-compose.base.yml        # Worker + RabbitMQ core stack
├── docker-compose.minio.yml       # MinIO storage overlay
├── docker-compose.local.yml       # Local bind mounts and dev-oriented defaults
├── .env.example
├── README.md
├── SPEC.md
└── assets/                        # Optional repo-level branding (often empty; UI assets live under ui/src/assets/)
```

Two Python packages in one uv workspace, plus the web UI. One repo. Responsibilities stay scoped to their package; internal file layout is an implementation detail.

---

## 18. Worker Architecture

The worker is a thin layer that turns DocRunr into a scalable document processing service for web applications.

**Purpose.** Web apps that need RAG-ready document processing should not embed heavy parsing logic. They upload a file, publish a job message, and get results back. The worker handles everything in between.

**Design.** The worker is intentionally minimal. It does three things:

1. Consume job messages from RabbitMQ
2. Call `docrunr.convert()` (the same Python API as the CLI)
3. Write extraction results to shared storage and publish a result message

It is not a framework. It has no plugin system. It does ship with a bundled operator UI for uploads, queue visibility, and artifact inspection.

**Scalability.** Horizontal scaling via multiple worker containers plus per-container concurrency. `WORKER_CONCURRENCY=1` keeps the inline single-job path. `WORKER_CONCURRENCY=N` allows up to `N` extraction jobs at once inside one worker process by using child processes, and RabbitMQ `prefetch_count` is set to the same `N`. Approximate total in-flight capacity is `replicas × WORKER_CONCURRENCY`, so you can scale with `docker compose up --scale worker=N` and tune per-worker concurrency independently.

**Reliability.** Manual acknowledgment — extraction messages are acked only after a result is successfully published. If a worker crashes mid-job, RabbitMQ redelivers the message to another worker. Per-job timeouts via `JOB_TIMEOUT_SECONDS` prevent stuck jobs.

**Integration.** RabbitMQ remains the main queue integration point, and the worker also exposes a minimal HTTP surface for health, stats, uploads, job history, and artifact access. Web apps can publish jobs directly to RabbitMQ or use the upload endpoint/UI as a thin convenience layer.

---

## 19. Job Protocol

### Queues

| Queue             | Direction         | Purpose                                      |
| ----------------- | ----------------- | -------------------------------------------- |
| `docrunr.jobs`    | Web app → Worker  | Job requests                                 |
| `docrunr.results` | Worker → Web app  | Processing results                           |
| `docrunr.dlq`     | Worker → Operator | Dead-lettered messages after bounded retries |

All queues are durable. Messages use `delivery_mode=2` (persistent). The `docrunr.jobs` queue is a **priority queue**: declare it with `arguments: {"x-max-priority": 255}` and set AMQP `BasicProperties.priority` on published jobs to match the JSON payload (see below). `docrunr.results` and `docrunr.dlq` are standard queues without priority arguments.

### Job Message

Published by the web app to `docrunr.jobs`:

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "filename": "Q1 Financial Report.pdf",
  "source_path": "input/2026/03/15/14/a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf",
  "options": {
    "some_option": 500
  },
  "priority": 0
}
```

- `job_id` — UUID generated by the web app. Also the filename stem on storage.
- `filename` — original human-readable name. Metadata only. Never written to disk.
- `source_path` — relative path within shared storage to the uploaded file.
- `options` — optional JSON object for future or app-specific overrides. The example key is illustrative only; the worker does not define stable option keys here and may ignore entries until a key is explicitly documented.
- `priority` — optional integer `0..255` (default `0`). Must be a JSON integer (not a float or string). Invalid values make the payload malformed. The worker maps this to AMQP message priority on the wire; the same value is echoed on result messages and in `/api/jobs` rows.

### Result Message

Published by the worker to `docrunr.results`:

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "ok",
  "filename": "Q1 Financial Report.pdf",
  "source_path": "input/2026/03/15/14/a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf",
  "markdown_path": "output/2026/03/15/14/a1b2c3d4-e5f6-7890-abcd-ef1234567890.md",
  "chunks_path": "output/2026/03/15/14/a1b2c3d4-e5f6-7890-abcd-ef1234567890.json",
  "total_tokens": 4830,
  "chunk_count": 12,
  "duration_seconds": 2.41,
  "error": null,
  "priority": 0
}
```

On failure, `status` is `"error"`, `markdown_path` and `chunks_path` are `null`, and `error` contains the failure message. `priority` repeats the value from the job request (or `0` when the job id was synthetic due to a malformed payload).

### Delivery Guarantees

At-least-once delivery.

- Extraction path: worker publishes to `docrunr.results`; extraction delivery is acked only after publish succeeds.
- If result publish fails, the extraction message is nacked with `requeue=true` and retried.

**Dead-letter queue.** Messages that fail on both the initial delivery and the automatic redelivery are published to `docrunr.dlq` (configurable via `RABBITMQ_DLQ_QUEUE`) with `delivery_mode=2`. The original message body is preserved verbatim; headers `x-docrunr-source-queue`, `x-docrunr-reason`, and `x-docrunr-failed-at` identify the origin and failure. Operators can inspect DLQ messages and re-publish them to the source queue for replay. If publishing to the DLQ itself fails, the message is nacked with `requeue=true` to avoid silent loss. Normal business failures that produce `status: "error"` results are not dead-lettered — they complete the request/reply cycle normally.

Consumers must be prepared for duplicate messages and duplicate processing. Handling is idempotent by design: same UUID produces the same extraction output paths.

**Worker UI aggregate stats.** Dashboard counters (`processed`, `failed`, average duration on `/stats` and `/api/overview`) are transition-aware: a replay after an earlier **successful** completion for the same `job_id` does not increment those totals again. After a terminal **error**, a later attempt that reaches a new terminal outcome can still update the counters—so genuine retries remain visible in aggregates.

**Malformed job messages.** Payloads that fail validation never appear on the result queue with a client-supplied `job_id`; the worker assigns a synthetic id that includes a per-delivery suffix so identical invalid bytes on separate deliveries show up as separate rows in `/api/jobs` history.

---

## 20. Shared Storage

The worker and web app communicate files through shared storage. Two backends are supported:

| Backend | Use case                     | Configuration                                   |
| ------- | ---------------------------- | ----------------------------------------------- |
| `local` | Docker volumes, NFS mounts   | `STORAGE_TYPE=local`, `STORAGE_BASE_PATH=/data` |
| `minio` | S3-compatible object storage | `STORAGE_TYPE=minio`, `MINIO_*` env vars        |

### Path Convention

Files use **time-partitioned, UUID-named paths** to prevent collisions and keep filenames unrecognizable:

```
<base_path>/
├── input/
│   └── 2026/
│       └── 03/
│           └── 15/
│               └── 14/
│                   ├── a1b2c3d4-...-.pdf
│                   └── e5f6a7b8-...-.docx
└── output/
    └── 2026/
        └── 03/
            └── 15/
                └── 14/
                    ├── a1b2c3d4-...-.md
                    └── a1b2c3d4-...-.json
```

- **Web app** generates a UUID, stores the uploaded file at `input/YYYY/MM/DD/HH/<uuid>.<ext>` (UTC).
- **Worker** writes output to `output/YYYY/MM/DD/HH/<uuid>.md` and `output/YYYY/MM/DD/HH/<uuid>.json`.
- **Original filenames** are never stored on disk. They exist only in message metadata.
- The `YYYY/MM/DD/HH/` prefix keeps directories from growing unbounded and simplifies cleanup/archival. Older objects may still use a shallower `YYYY/MM/...` layout; the worker accepts both.

---

## 21. Configuration

All worker settings are environment variables. No config files. No CLI flags.

| Variable                | Default           | Description                                                                                                                                           |
| ----------------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `RABBITMQ_HOST`         | `rabbitmq`        | RabbitMQ hostname                                                                                                                                     |
| `RABBITMQ_PORT`         | `5672`            | RabbitMQ port                                                                                                                                         |
| `RABBITMQ_USER`         | `guest`           | RabbitMQ username                                                                                                                                     |
| `RABBITMQ_PASSWORD`     | `guest`           | RabbitMQ password                                                                                                                                     |
| `RABBITMQ_QUEUE`        | `docrunr.jobs`    | Input job queue name                                                                                                                                  |
| `RABBITMQ_RESULT_QUEUE` | `docrunr.results` | Result queue name                                                                                                                                     |
| `RABBITMQ_DLQ_QUEUE`    | `docrunr.dlq`     | Dead-letter queue name for messages that fail after bounded retries                                                                                   |
| `STORAGE_TYPE`          | `local`           | Storage backend: `local` or `minio`                                                                                                                   |
| `STORAGE_BASE_PATH`     | `/data`           | Base path for local storage                                                                                                                           |
| `MINIO_ENDPOINT`        | `minio:9000`      | MinIO server endpoint                                                                                                                                 |
| `MINIO_ACCESS_KEY`      |                   | MinIO access key                                                                                                                                      |
| `MINIO_SECRET_KEY`      |                   | MinIO secret key                                                                                                                                      |
| `MINIO_BUCKET`          | `docrunr`         | MinIO bucket name                                                                                                                                     |
| `MINIO_SECURE`          | `false`           | Use TLS for MinIO                                                                                                                                     |
| `JOB_TIMEOUT_SECONDS`   | `120`             | Per-job processing timeout                                                                                                                            |
| `HEALTH_PORT`           | `8080`            | Health endpoint HTTP port                                                                                                                             |
| `SQLITE_BASE_PATH`      | `/db`             | Base path for SQLite worker UI persistence; worker stores DB at `<base>/<hostname>/docrunr.sqlite`                                                    |
| `UI_PASSWORD`           | (empty)           | If non-empty, enables optional HTTP session auth (bundled UI uses a password form + cookie) for `/api/jobs`, `/api/artifact`, and `POST /api/uploads` |

---

## 22. Health and Stats

The worker runs a minimal HTTP server on `HEALTH_PORT` (default 8080) for liveness checks and operational visibility.

When `UI_PASSWORD` is unset, behavior matches the open dashboard defaults: every HTTP route behaves as documented below. When `UI_PASSWORD` is set, the worker issues `HttpOnly` `SameSite=Lax` session cookies with an internal fixed TTL.

| Endpoint                | Content-Type                          | Purpose                                                                                                                                          |
| ----------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| `GET /`                 | `text/html`                           | Human-readable dashboard                                                                                                                         |
| `GET /health`           | `application/json`                    | Liveness check for Docker / load balancers                                                                                                       |
| `GET /stats`            | `application/json`                    | Processing counters for monitoring                                                                                                               |
| `GET /api/overview`     | `application/json`                    | Combined health/stats payload for UI                                                                                                             |
| `GET /api/auth/session` | `application/json`                    | `auth_enabled`, `authenticated` for the bundled UI                                                                                               |
| `POST /api/auth/login`  | `application/json`                    | JSON body `password`; sets session cookie on success                                                                                             |
| `POST /api/auth/logout` | `application/json`                    | Revokes server session and clears cookie                                                                                                         |
| `POST /api/uploads`     | `application/json`                    | Multipart upload (`files` / `file` fields); optional query `priority=0..255` sets job and AMQP priority (default `0`; invalid values → HTTP 400) |
| `GET /api/jobs`         | `application/json`                    | Persistent job list (`limit`, `status`, `search`); items include `priority`                                                                      |
| `GET /api/artifact`     | `text/markdown` or `application/json` | Open output artifact by path (`output/...md                                                                                                      | json`) |

### `GET /api/jobs`

Jobs are listed with `status` of `processing` while work is in flight, then `ok` or `error` when terminal. Filter with `status` (`ok`, `error`, `processing`, or omit for all).

Response items include lifecycle timestamps when present: `received_at` (worker accepted the message), `finished_at` (terminal outcome recorded; omitted while still `processing`), and `updated_at` (last row update). These fields sit alongside the same result-oriented shape as the queue result message (`job_id`, paths, `duration_seconds`, `error`, `priority`, etc.).

### `/health` response

```json
{
  "status": "ok",
  "rabbitmq": "connected",
  "uptime_seconds": 3421
}
```

### `/stats` response

```json
{
  "processed": 47,
  "failed": 2,
  "avg_duration_seconds": 3.1,
  "last_job_at": "2026-03-21T14:22:00Z"
}
```

Job history and aggregate UI stats are persisted in SQLite under
`<SQLITE_BASE_PATH>/<hostname>/docrunr.sqlite` (default base path: `/db`), so dashboard data
survives worker restarts.

The health server uses Python's stdlib `http.server`. No framework. No external dependency.

---

## 23. Future Considerations

These may be added later. They must not increase CLI complexity.

- Improved table reconstruction
- Image caption extraction
- Metadata extraction (author, date, title)
- Custom parser plugins
- Streaming / large file support
- Upload UI controls for job priority (API and RabbitMQ already support `priority`)
- Result TTL and automatic cleanup

---

## 24. Success Criteria

DocRunr succeeds when:

A developer runs `docrunr file.pdf` and gets clean, usable Markdown and chunks — without reading docs, without configuring anything, without debugging extraction failures.

A web app developer runs `docker compose up`, publishes a job to RabbitMQ, and gets processed results back — without writing document parsing code, without managing extraction dependencies, without building a custom worker.

The tool should eliminate the need for custom document ingestion scripts in RAG pipelines.

That moment of "this just works" is the entire product.

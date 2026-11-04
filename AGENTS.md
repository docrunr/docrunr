# Agent rules

DocRunr is a uv workspace that turns documents into Markdown and chunks:

```text
Documents -> RabbitMQ -> worker (core pipeline) -> Markdown + chunks JSON
                |                 |
                v                 v
              api (optional HTTP)  worker-llm (optional embeddings via LiteLLM)
```

```text
core        CLI + library (`docrunr` on PyPI): detect -> parse -> clean -> chunk
runtime     storage and messaging primitives
api         local HTTP gateway + checked-in OpenAPI (`/api/v1`)
worker      TXT RabbitMQ worker, health, bundled operator UI
worker-llm  optional embedding worker
ui          React/Mantine (pnpm); talks to worker/API HTTP only
tests/      core, runtime, api, worker, worker_llm, integration, samples
```

## Source of truth

Agent guidance lives only in this file. Do not add `.cursor/rules`, `.cursor/skills`,
or other tool-specific copies.

`SPEC.md` is the product contract. A behavior change updates `SPEC.md` in the same PR.
`CONTRIBUTING.md` is for human contributors.

## Principles

- Make the smallest change that solves the problem, and prefer deleting code to adding it.
  When clarity is equal, fewer lines win.
- Subtract before you add: one place per rule or helper. Do not design for rare or future
  cases nobody asked about.
- Minimize reader load: match the naming, structure, and libraries already near the change.
- Validate at the boundaries (HTTP input, queue payloads, env). Trust internal types inside
  a package.
- Prove it works: run the check that exercises the real behavior. Cite the command and its
  output.
- Test behavior, not implementation. Keep tests that pin parser fallback, queue contracts,
  OpenAPI, and user-visible failure modes.
- Use the existing tooling: `uv`, `pnpm` (UI only), the Makefile, and `scripts/*.mjs`.
  Do not add another package manager or a parallel script.
- For non-trivial changes, add a short decision log to the PR body: the options, the choice,
  and the reason.

DocRunr guarantees (SPEC §3–4; breaking them needs a major version):

- Identical inputs always produce identical outputs.
- One bad file never crashes a batch.
- Core extraction is local: no hosted APIs or telemetry in conversion.
- Parser fallbacks are automatic (quality gate). The user sees clean output, not a fallback.
- Output is valid UTF-8 Markdown. The chunk JSON schema is stable.
- Opinionated defaults: no tuning dials, one chunking approach (recursive, structure-based,
  no overlap).

## Layer boundaries

- **core** does not import `worker`, `api`, or `runtime`. Parsers live in
  `core/src/docrunr/parsers` and register through the registry. Shared converter helpers
  stay in `parsers/_converters.py`.
- **runtime** owns the storage and queue contract. Workers and the API talk to
  infrastructure through it.
- **api** is an optional gateway: store the upload, publish the job, project results over
  HTTP. It exclusively consumes `docrunr.results`, `docrunr.llm.results`, and
  `docrunr.lifecycle`.
- **worker** consumes `docrunr.jobs`, calls `docrunr.convert()`, writes artifacts, and
  publishes results. It is not a plugin framework.
- **worker-llm** is optional. Pass `llm_profile` on the extraction job to trigger embeddings.
- **ui** talks only to worker/API HTTP endpoints. Use `pnpm -C ui …`; CI uses pnpm@9.

## Dependencies

- One `uv lock` for the workspace. Keep versions inside `requires-python`
  (`>=3.11,<3.14`). Docker base images stay on that range (`python:3.13-slim` today).
- `torch` and `torchvision` come from the `pytorch-cpu` index and move together.
- Fold Dependabot bumps into one PR with one lockfile. Do not merge lockfile-only
  branches one by one.
- UI uses pnpm only. Python uses uv only.

## Done means

After the last edit, run `make lint` first (it can modify files), then:

```bash
make lint
make test
make test-api
make skylos
```

`make lint` runs ruff plus mypy on `runtime`, `api`, `core`, and `worker` (not
`worker-llm`), then UI lint/format/typecheck.

When UI source changes, also `make fallow`. When parsers or the pipeline change,
`make test-samples`. When the worker, API, or Compose changes, start the stack
(`make docker-run`, `PROFILE=local`) and run:

- `make test-integration-txt` — stop the API overlay first (`docker stop docrunr-api-1`)
  so it does not consume `docrunr.results`
- `make test-integration-api` — start the API overlay again

`make test-integration-llm` / `make test-integration-s3` only when that path is touched.

mypy is strict; ruff line length is 100. A `noqa` or `type: ignore` needs a reason.
Host OCR tests skip without tessdata; the worker image ships Tesseract `eng`+`nld`.
Cite the command and its report.

## Git / PRs

Conventional commits (`fix(worker): …`, `feat(core): …`). Open PRs against the
agreed base (`main` or `release/*`). Releases are tag-driven from `main` via
`make release`. CI: `.github/workflows/ci.yml`.

## More

- Product contract: `SPEC.md`
- Human contributing: `CONTRIBUTING.md`
- Architecture overview: `README.md`

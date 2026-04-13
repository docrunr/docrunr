# Contributing to DocRunr

Thanks for contributing.
This guide keeps contributions simple, consistent, and easy to review.

## Ground Rules

- Be respectful and constructive. See [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).
- Keep pull requests focused and small when possible.
- Prefer clarity over cleverness in code and docs.
- Add or update tests for behavioral changes.

## Repository structure

- **`core/`** — `docrunr` (CLI + library, PyPI).
- **`worker/`** — `docrunr-worker` (RabbitMQ, storage, HTTP; PyPI + Docker entrypoint).
- **`ui/`** — React/Mantine app; `pnpm -C ui dev` proxies API routes to the worker on port 8080.
- **`tests/`** — `core`, `worker`, `integration` (needs services), `samples`.

## Local Setup

1. Install Python 3.11+ and `uv`.
2. Clone the repository.
3. Run:

```bash
uv sync --dev
```

## Development Workflow

1. Create a branch from the active release line or agreed base branch.
2. Make changes with tests.
3. Run quality checks locally:

```bash
uv run ruff check .
uv run mypy .
uv run pytest -q
```

4. Open a pull request to `release/*` unless maintainers ask otherwise.

## Pull Request Checklist

- Problem and solution are clearly explained.
- Lint, type checks, and tests pass locally.
- New behavior has tests.
- Documentation is updated when needed.
- No unrelated refactors mixed into the same PR.

## Commit Messages

Use clear, descriptive messages.
Examples:

- `fix(worker): handle invalid job payloads`
- `feat(core): improve markdown chunk heading retention`
- `docs: clarify release flow`

## CI and Release Model

- CI runs on `release/**` branches.
- Release is tag-driven (`vX.Y.Z`) from `main`.
- Use VS Code task `release` (or `./scripts/release.sh`) on `main` to create/push tags.
- Publishing on release tags:
  - PyPI: `docrunr` (CLI/library)
  - Docker: worker image (multi-arch `amd64` + `arm64`)

## Reporting Bugs and Suggesting Features

When opening an issue, include:

- Expected behavior
- Actual behavior
- Reproduction steps
- Environment details (OS, Python version, command used)

For parser/extraction issues, attach a minimal sample file when possible.

## Security

Do not open public issues for sensitive vulnerabilities.
Use GitHub private security advisories for responsible disclosure.

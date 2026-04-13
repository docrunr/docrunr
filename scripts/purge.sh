#!/usr/bin/env bash
set -euo pipefail

# Reset local workspace artifacts (Docker named volumes, UI deps, Python/tool caches).
# Preserves source, .venv, and bind-mounted .data/. Run from repo root.

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
cd "$repo_root"

echo "==> docker compose down --remove-orphans"
docker compose down --remove-orphans

echo "==> removing Docker volumes named docrunr-*"
docrunr_volumes=()
while IFS= read -r vol; do
  [[ -n "$vol" ]] && docrunr_volumes+=("$vol")
done < <(docker volume ls -q | grep '^docrunr-' || true)
if ((${#docrunr_volumes[@]})); then
  docker volume rm "${docrunr_volumes[@]}"
else
  echo "    (none)"
fi

if [[ -d ui/node_modules ]]; then
  echo "==> removing ui/node_modules"
  rm -rf ui/node_modules
else
  echo "==> ui/node_modules (already absent)"
fi

echo "==> removing Python/tool cache directories"
while IFS= read -r -d '' dir; do
  rm -rf "$dir"
done < <(find . -type d \( \
  -name __pycache__ -o \
  -name .pytest_cache -o \
  -name .mypy_cache -o \
  -name .ruff_cache -o \
  -name .uv-cache \
\) -print0)

echo "Purge done."

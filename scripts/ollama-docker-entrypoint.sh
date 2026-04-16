#!/bin/sh
# DocRunr: used only when layering docker-compose.ollama.yml.
# Starts a transient Ollama daemon, pulls configured models (HTTP API does not auto-pull),
# then execs `ollama serve` as PID 1 for correct signal handling.
#
# Models to pull (comma-separated, no spaces inside names):
#   1) OLLAMA_EMBED_MODELS if non-empty — e.g. "nomic-embed-text,llama3.2"
#   2) else OLLAMA_EMBED_MODEL — single name, default nomic-embed-text
set -e

ollama serve &
SERVE_PID=$!

echo "[ollama-entrypoint] waiting for daemon (pid ${SERVE_PID})..."
i=0
while [ "$i" -lt 180 ]; do
  if ollama list >/dev/null 2>&1; then
    echo "[ollama-entrypoint] daemon is up."
    break
  fi
  i=$((i + 1))
  sleep 1
done

if ! ollama list >/dev/null 2>&1; then
  echo "[ollama-entrypoint] Ollama did not become ready in time." >&2
  kill "$SERVE_PID" 2>/dev/null || true
  exit 1
fi

if [ -n "${OLLAMA_EMBED_MODELS:-}" ]; then
  _raw="$OLLAMA_EMBED_MODELS"
else
  _raw="${OLLAMA_EMBED_MODEL:-nomic-embed-text}"
fi

echo "[ollama-entrypoint] ensuring models (from env): ${_raw}"

_old_ifs=$IFS
IFS=,
for _m in $_raw; do
  _m=$(printf '%s' "$_m" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  if [ -z "$_m" ]; then
    continue
  fi
  echo "[ollama-entrypoint] pulling ${_m} (no-op if already present)..."
  ollama pull "$_m"
done
IFS=$_old_ifs

echo "[ollama-entrypoint] handing off to ollama serve (exec, pid 1)..."
kill "$SERVE_PID"
wait "$SERVE_PID" 2>/dev/null || true
sleep 1

exec ollama serve

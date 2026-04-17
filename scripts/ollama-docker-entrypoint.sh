#!/bin/sh
# DocRunr: used only when layering docker-compose.ollama.yml.
# Starts a transient Ollama daemon, pulls configured models (HTTP API does not auto-pull),
# then execs `ollama serve` as PID 1 for correct signal handling.
#
# Models to pull (comma-separated, no spaces inside names):
#   OLLAMA_EMBED_MODELS — must match the Ollama model tags litellm.yaml maps from.
#   The litellm model names (ege-m3-560m, etc.) are litellm aliases; the underlying
#   Ollama model tags are the values in litellm.yaml's `model: ollama/<tag>`.
#   Always use the Ollama-native tag (e.g. "bge-m3", NOT "bge-m3-560m").
#   Example: "nomic-embed-text,bge-m3,embeddinggemma,qwen3-embedding:8b"
#   Falls back to "nomic-embed-text" when empty.
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

_raw="${OLLAMA_EMBED_MODELS:-nomic-embed-text}"

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

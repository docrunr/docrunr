"""LiteLLM client wrapper — all embedding and LLM calls go through LiteLLM."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docrunr_worker_llm.config import LlmWorkerSettings

logger = logging.getLogger(__name__)


class LitellmError(Exception):
    """Wrapper for LiteLLM API errors."""


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    llm_profile: str
    provider: str
    token_count: int


def create_embeddings(
    texts: list[str],
    *,
    settings: LlmWorkerSettings,
    llm_profile: str,
) -> EmbeddingResult:
    """Request embeddings from LiteLLM for a batch of text chunks.

    ``llm_profile`` is passed directly as the LiteLLM ``model`` parameter —
    it must match a ``model_name`` exposed by the LiteLLM proxy.
    """
    import litellm

    if not llm_profile:
        raise LitellmError("llm_profile is required but was empty")

    api_base = settings.litellm_base_url or None
    api_key = settings.litellm_api_key or None
    timeout = settings.litellm_timeout_seconds

    # When routing through a LiteLLM proxy, the proxy exposes an
    # OpenAI-compatible API.  The litellm library needs the "openai/"
    # prefix so it uses the right request format; the proxy then resolves
    # the model_name alias internally.  The OpenAI client also requires
    # an api_key — use a dummy value when none is configured since the
    # proxy itself handles auth to the upstream provider.
    if api_base:
        model = f"openai/{llm_profile}"
        if not api_key:
            api_key = "sk-not-needed"
    else:
        model = llm_profile

    try:
        response = litellm.embedding(
            model=model,
            input=texts,
            api_base=api_base,
            api_key=api_key,
            timeout=timeout,
        )
    except Exception as exc:
        logger.error("LiteLLM embedding call failed: %s", exc)
        raise LitellmError(str(exc)) from exc

    vectors: list[list[float]] = []
    for item in response.data:
        vectors.append(item["embedding"])

    usage = getattr(response, "usage", None)
    token_count = 0
    if usage is not None:
        token_count = getattr(usage, "total_tokens", 0) or 0

    provider = _infer_provider(llm_profile)

    return EmbeddingResult(
        vectors=vectors,
        llm_profile=llm_profile,
        provider=provider,
        token_count=token_count,
    )


def _infer_provider(llm_profile: str) -> str:
    """Best-effort provider label from profile string (e.g. ``ollama/nomic-embed`` → ``ollama``)."""
    if "/" in llm_profile:
        return llm_profile.split("/", 1)[0]
    return "openai"

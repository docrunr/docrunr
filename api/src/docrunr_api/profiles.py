"""Cached LiteLLM profile discovery."""

from __future__ import annotations

import asyncio
import time

import httpx

from docrunr_api.config import ApiSettings


class ProfilesUnavailableError(RuntimeError):
    pass


class LlmProfileClient:
    def __init__(self, settings: ApiSettings) -> None:
        self._settings = settings
        self._cache: tuple[float, list[str]] | None = None
        self._lock = asyncio.Lock()

    async def list_profiles(self) -> list[str]:
        if not self._settings.litellm_base_url.strip():
            raise ProfilesUnavailableError("LiteLLM is not configured")
        now = time.monotonic()
        if self._cache and self._cache[0] > now:
            return list(self._cache[1])
        async with self._lock:
            now = time.monotonic()
            if self._cache and self._cache[0] > now:
                return list(self._cache[1])
            headers: dict[str, str] = {}
            if self._settings.litellm_api_key:
                headers["Authorization"] = f"Bearer {self._settings.litellm_api_key}"
            try:
                async with httpx.AsyncClient(
                    timeout=self._settings.litellm_timeout_seconds
                ) as client:
                    response = await client.get(
                        f"{self._settings.litellm_base_url.rstrip('/')}/models",
                        headers=headers,
                    )
                    response.raise_for_status()
                    body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ProfilesUnavailableError("LiteLLM is unavailable") from exc
            profiles = sorted(
                {
                    str(item["id"]).strip()
                    for item in body.get("data", [])
                    if isinstance(item, dict) and str(item.get("id", "")).strip()
                }
            )
            self._cache = (
                now + self._settings.litellm_profiles_cache_seconds,
                profiles,
            )
            return profiles

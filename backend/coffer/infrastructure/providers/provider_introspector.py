"""Outbound provider introspection adapter (spec 008/006).

Implements ``application.providers.ports.ProviderIntrospectionPort``. One
OpenAI-compatible ``AsyncOpenAI`` client (base_url swapped per provider) powers
list-models + the chat/embedding test calls; Anthropic uses its own REST shape.
Every non-local outbound URL passes the SSRF guard first; the machine-local
providers (ollama/lmstudio/local) are exempt because their base URL is loopback,
which the guard otherwise blocks.
"""

from __future__ import annotations

import asyncio

import httpx

from coffer.application.providers.ports import LOCAL_PROVIDERS
from coffer.infrastructure.skill.ssrf_guard import check_url

#: Default base URL per provider (None = the SDK's own default, i.e. OpenAI).
PROVIDER_BASE_URLS: dict[str, str | None] = {
    "openai": None,
    "anthropic": "https://api.anthropic.com",
    "openrouter": "https://openrouter.ai/api/v1",
    "voyage": "https://api.voyageai.com/v1",
    "jina": "https://api.jina.ai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "azure": None,
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
    "local": None,
}

_ANTHROPIC_VERSION = "2023-06-01"
_TIMEOUT = 15.0


class ProviderIntrospector:
    """Implements ``ProviderIntrospectionPort`` over OpenAI-compatible HTTP."""

    def _base_url(self, provider: str, base_url: str | None) -> str | None:
        return base_url or PROVIDER_BASE_URLS.get(provider)

    async def _guard(self, provider: str, url: str | None) -> None:
        # Local providers point at loopback (which the guard blocks); exempt them.
        if provider in LOCAL_PROVIDERS or not url:
            return
        await asyncio.to_thread(check_url, url)

    def _openai_client(self, base_url: str | None, api_key: str | None):  # type: ignore[no-untyped-def]
        from openai import AsyncOpenAI

        return AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url, timeout=_TIMEOUT)

    async def list_models(
        self, *, provider: str, base_url: str | None, api_key: str | None
    ) -> list[str]:
        url = self._base_url(provider, base_url)
        await self._guard(provider, url)
        if provider == "anthropic":
            return await self._anthropic_models(url, api_key)
        client = self._openai_client(url, api_key)
        page = await client.models.list()
        return [m.id for m in page.data]

    async def _anthropic_models(self, base_url: str | None, api_key: str | None) -> list[str]:
        root = (base_url or "https://api.anthropic.com").rstrip("/")
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{root}/v1/models",
                headers={"x-api-key": api_key or "", "anthropic-version": _ANTHROPIC_VERSION},
            )
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", [])]

    async def test_chat(
        self, *, provider: str, model: str, base_url: str | None, api_key: str | None
    ) -> None:
        url = self._base_url(provider, base_url)
        await self._guard(provider, url)
        if provider == "anthropic":
            await self._anthropic_test(url, model, api_key)
            return
        client = self._openai_client(url, api_key)
        await client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": "ping"}], max_tokens=1
        )

    async def _anthropic_test(self, base_url: str | None, model: str, api_key: str | None) -> None:
        root = (base_url or "https://api.anthropic.com").rstrip("/")
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{root}/v1/messages",
                headers={"x-api-key": api_key or "", "anthropic-version": _ANTHROPIC_VERSION},
                json={
                    "model": model,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "ping"}],
                },
            )
            r.raise_for_status()

    async def test_embedding(
        self, *, provider: str, model: str, base_url: str | None, api_key: str | None
    ) -> int:
        url = self._base_url(provider, base_url)
        await self._guard(provider, url)
        client = self._openai_client(url, api_key)
        resp = await client.embeddings.create(model=model, input="test")
        return len(resp.data[0].embedding)

"""Outbound provider introspection adapter (specs channels and knowledge).

Implements ``application.provider.ports.ProviderIntrospectionPort``. One
OpenAI-compatible ``AsyncOpenAI`` client (base_url swapped per protocol) powers
list-models + the chat test call; Anthropic uses its own REST shape. Every
non-local outbound URL passes the SSRF guard first; the machine-local ``ollama``
protocol is exempt because its base URL is loopback, which the guard otherwise
blocks.
"""

from __future__ import annotations

import asyncio

import httpx

from coffer.application.provider.ports import ListedModel
from coffer.domain.provider.config import is_loopback_url
from coffer.domain.usage.pricing import ModelPrice
from coffer.infrastructure.net.ssrf_guard import check_url

#: Default base URL per WIRE PROTOCOL (None = the SDK's own default, i.e.
#: OpenAI). The key is a ``domain.provider.config.Protocol`` value — a wire
#: Coffer DETECTED, never a vendor id: every caller of this adapter reaches it
#: through ``POST /api/v1/models/*``, whose ``provider`` field the connection
#: editors fill from the connection's ``protocol``. ``unknown`` is absent on
#: purpose: an unclassified endpoint has no default, so its base URL must be the
#: one the user typed.
PROTOCOL_BASE_URLS: dict[str, str | None] = {
    "openai": None,
    "anthropic": "https://api.anthropic.com",
    "ollama": "http://localhost:11434/v1",
}

_ANTHROPIC_VERSION = "2023-06-01"
#: One attempt, one budget. A probe is something a person is waiting on with a
#: spinner, so it answers once: the OpenAI SDK's default two retries turned a
#: single slow model into a 46-second wait before "Request timed out.". The
#: budget is long enough for a reasoning model's first reply to a one-token
#: request, since there is no retry behind it.
_TIMEOUT = 30.0

_PER_MTOK = 1_000_000


def _per_mtok(value: object) -> float | None:
    """A per-token USD rate (OpenRouter sends strings) as USD per 1M tokens;
    ``None`` for a missing, malformed or negative ("varies") rate."""
    try:
        rate = float(str(value))
    except (TypeError, ValueError):
        return None
    if rate < 0:
        return None
    return round(rate * _PER_MTOK, 6)


def reported_price(extra: dict[str, object] | None) -> ModelPrice | None:
    """The price a ``/models`` entry reports, OpenRouter's shape: a
    ``pricing`` object of per-token rates (``prompt``, ``completion``,
    ``input_cache_read``, ``input_cache_write``). ``None`` when the entry
    carries no usable input and output rate."""
    pricing = (extra or {}).get("pricing")
    if not isinstance(pricing, dict):
        return None
    prompt = _per_mtok(pricing.get("prompt"))
    completion = _per_mtok(pricing.get("completion"))
    if prompt is None or completion is None:
        return None
    return ModelPrice(
        input=prompt,
        output=completion,
        cache_read=_per_mtok(pricing.get("input_cache_read")),
        cache_write_5m=_per_mtok(pricing.get("input_cache_write")),
    )


class ProviderIntrospector:
    """Implements ``ProviderIntrospectionPort`` over OpenAI-compatible HTTP."""

    def _base_url(self, provider: str, base_url: str | None) -> str | None:
        # ``provider`` is the connection's detected wire protocol, not a vendor.
        return base_url or PROTOCOL_BASE_URLS.get(provider)

    async def _guard(self, provider: str, url: str | None) -> None:
        # Only a URL that really is loopback is exempt (a local runtime). The
        # exemption follows the URL, never the declared protocol: ``provider`` is
        # whatever the caller sent, and "ollama" must not switch the guard off.
        if not url or is_loopback_url(url):
            return
        await asyncio.to_thread(check_url, url)

    def _openai_client(self, base_url: str | None, api_key: str | None):  # type: ignore[no-untyped-def]
        from openai import AsyncOpenAI

        return AsyncOpenAI(
            api_key=api_key or "not-needed",
            base_url=base_url,
            timeout=_TIMEOUT,
            max_retries=0,
        )

    async def list_models(
        self, *, provider: str, base_url: str | None, api_key: str | None
    ) -> list[str | ListedModel]:
        url = self._base_url(provider, base_url)
        await self._guard(provider, url)
        if provider == "anthropic":
            return list(await self._anthropic_models(url, api_key))
        client = self._openai_client(url, api_key)
        page = await client.models.list()
        return [ListedModel(id=m.id, price=reported_price(m.model_extra)) for m in page.data]

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

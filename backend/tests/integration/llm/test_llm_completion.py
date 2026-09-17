"""Integration test for LangchainLlmCompletion — monkeypatches build_chat_model."""

from __future__ import annotations

import pytest

from coffer.domain.provider.config import Protocol, ProviderConfig, ResolvedConnection
from coffer.infrastructure.llm import llm_completion


@pytest.mark.asyncio
async def test_complete_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        content = "completed"

    class _Model:
        async def ainvoke(self, messages: object) -> _Resp:
            return _Resp()

    # Records the bound: the port's whole job here is to carry the operator's
    # timeout down to the client, and a stub that merely tolerated the keyword
    # would pass whether or not it arrived.
    seen: dict[str, object] = {}

    def _build(cfg: object, resolver: object, *, timeout: float | None = None) -> _Model:
        seen["timeout"] = timeout
        return _Model()

    monkeypatch.setattr(llm_completion, "build_chat_model", _build)

    port = llm_completion.LangchainLlmCompletion()
    cfg = ResolvedConnection(
        config=ProviderConfig(
            protocol=Protocol.OLLAMA,
            base_url="http://localhost:11434",
            credential_ref=None,
        ),
        model="llama3",
    )
    out = await port.complete(
        system="s", user="u", model=cfg, credential_resolver=lambda r: "", timeout=90.0
    )
    assert out == "completed"
    assert seen["timeout"] == 90.0

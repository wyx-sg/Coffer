"""Integration test for LangchainLlmCompletion — monkeypatches build_chat_model."""

from __future__ import annotations

import pytest

from coffer.domain.provider.config import Protocol, ProviderConfig, ResolvedConnection
from coffer.infrastructure.chat import llm_completion


@pytest.mark.asyncio
async def test_complete_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        content = "distilled"

    class _Model:
        async def ainvoke(self, messages: object) -> _Resp:
            return _Resp()

    monkeypatch.setattr(llm_completion, "build_chat_model", lambda cfg, resolver: _Model())

    port = llm_completion.LangchainLlmCompletion()
    cfg = ResolvedConnection(
        config=ProviderConfig(
            protocol=Protocol.OLLAMA,
            base_url="http://localhost:11434",
            credential_ref=None,
        ),
        model="llama3",
    )
    out = await port.complete(system="s", user="u", model=cfg, credential_resolver=lambda r: "")
    assert out == "distilled"

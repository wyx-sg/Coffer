"""Integration test for LangchainLlmCompletion — monkeypatches build_chat_model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.chat.model import ModelConfig, ProviderType
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
    cfg = ModelConfig(
        id="test-id",
        display_name="Test Ollama",
        provider=ProviderType.OLLAMA,
        model="llama3",
        credential_ref=None,
        base_url="http://localhost:11434",
        is_default=False,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    out = await port.complete(system="s", user="u", model=cfg, credential_resolver=lambda r: "")
    assert out == "distilled"

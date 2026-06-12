"""Unit tests for ModelConfig validation. Pure — no I/O."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.chat.model import ModelConfig, ProviderType
from coffer.domain.errors import ModelRejected


def _ts() -> datetime:
    return datetime(2026, 5, 22, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# ProviderType
# ---------------------------------------------------------------------------


def test_provider_type_values() -> None:
    assert ProviderType.ANTHROPIC == "anthropic"
    assert ProviderType.OPENAI == "openai"
    assert ProviderType.OLLAMA == "ollama"


# ---------------------------------------------------------------------------
# Valid constructions
# ---------------------------------------------------------------------------


def test_anthropic_with_credential() -> None:
    m = ModelConfig(
        id="m-001",
        display_name="My Claude",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="anthropic-key",
        base_url=None,
        is_default=True,
        created_at=_ts(),
        updated_at=_ts(),
    )
    assert m.provider == "anthropic"
    assert m.credential_ref == "anthropic-key"
    assert m.base_url is None


def test_openai_with_credential() -> None:
    m = ModelConfig(
        id="m-002",
        display_name="GPT-4o",
        provider=ProviderType.OPENAI,
        model="gpt-4o",
        credential_ref="openai-key",
        base_url=None,
        is_default=False,
        created_at=_ts(),
        updated_at=_ts(),
    )
    assert m.provider == "openai"
    assert m.credential_ref == "openai-key"


def test_ollama_with_base_url() -> None:
    m = ModelConfig(
        id="m-003",
        display_name="Local Llama",
        provider=ProviderType.OLLAMA,
        model="llama3.1",
        credential_ref=None,
        base_url="http://localhost:11434",
        is_default=False,
        created_at=_ts(),
        updated_at=_ts(),
    )
    assert m.provider == "ollama"
    assert m.base_url == "http://localhost:11434"
    assert m.credential_ref is None


# ---------------------------------------------------------------------------
# Validation rejects bad input
# ---------------------------------------------------------------------------


def test_anthropic_without_credential_raises_model_rejected() -> None:
    with pytest.raises(ModelRejected) as exc_info:
        ModelConfig(
            id="m-004",
            display_name="Claude Missing Cred",
            provider=ProviderType.ANTHROPIC,
            model="claude-sonnet-4-6",
            credential_ref=None,
            base_url=None,
            is_default=False,
            created_at=_ts(),
            updated_at=_ts(),
        )
    err = exc_info.value
    assert err.code == "MODEL_REJECTED"
    assert err.reason == "missing_credential"


def test_openai_without_credential_raises_model_rejected() -> None:
    with pytest.raises(ModelRejected) as exc_info:
        ModelConfig(
            id="m-005",
            display_name="GPT Missing Cred",
            provider=ProviderType.OPENAI,
            model="gpt-4o",
            credential_ref=None,
            base_url=None,
            is_default=False,
            created_at=_ts(),
            updated_at=_ts(),
        )
    assert exc_info.value.reason == "missing_credential"


def test_ollama_without_base_url_raises_model_rejected() -> None:
    with pytest.raises(ModelRejected) as exc_info:
        ModelConfig(
            id="m-006",
            display_name="Ollama No URL",
            provider=ProviderType.OLLAMA,
            model="llama3.1",
            credential_ref=None,
            base_url=None,
            is_default=False,
            created_at=_ts(),
            updated_at=_ts(),
        )
    assert exc_info.value.reason == "missing_base_url"


def test_empty_display_name_raises_model_rejected() -> None:
    with pytest.raises(ModelRejected) as exc_info:
        ModelConfig(
            id="m-007",
            display_name="",
            provider=ProviderType.ANTHROPIC,
            model="claude-sonnet-4-6",
            credential_ref="key-ref",
            base_url=None,
            is_default=False,
            created_at=_ts(),
            updated_at=_ts(),
        )
    assert exc_info.value.reason == "empty_display_name"


def test_whitespace_only_display_name_raises_model_rejected() -> None:
    with pytest.raises(ModelRejected) as exc_info:
        ModelConfig(
            id="m-008",
            display_name="   ",
            provider=ProviderType.ANTHROPIC,
            model="claude-sonnet-4-6",
            credential_ref="key-ref",
            base_url=None,
            is_default=False,
            created_at=_ts(),
            updated_at=_ts(),
        )
    assert exc_info.value.reason == "empty_display_name"


# ---------------------------------------------------------------------------
# ModelConfig is frozen
# ---------------------------------------------------------------------------


def test_model_config_frozen() -> None:
    m = ModelConfig(
        id="m-009",
        display_name="Frozen Test",
        provider=ProviderType.ANTHROPIC,
        model="claude-sonnet-4-6",
        credential_ref="ref",
        base_url=None,
        is_default=False,
        created_at=_ts(),
        updated_at=_ts(),
    )
    with pytest.raises((AttributeError, TypeError)):
        m.display_name = "changed"  # type: ignore[misc]

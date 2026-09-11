"""ProviderConfig validation tests (spec provider-switching). Pure — unit tier."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import Protocol, ProviderConfig


def test_valid_config_defaults() -> None:
    c = ProviderConfig(
        protocol="anthropic",  # type: ignore[arg-type]
        base_url="https://x",
        credential_ref="provider/acme/key",
    )
    assert c.protocol is Protocol.ANTHROPIC
    assert c.is_active is False
    assert c.internal_default is False


def test_unknown_protocol_member_is_valid() -> None:
    # ``unknown`` is a first-class protocol (the probe was inconclusive); a
    # connection with it still requires a credential like any cloud wire.
    c = ProviderConfig(
        protocol="unknown",  # type: ignore[arg-type]
        base_url="https://x",
        credential_ref="r",
    )
    assert c.protocol is Protocol.UNKNOWN


def test_bogus_protocol_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="bogus",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="r",
        )


def test_empty_base_url_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="   ",
            credential_ref="r",
        )


def test_malformed_credential_ref_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="bad ref!",
        )


def test_ollama_must_not_carry_credential() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="ollama",  # type: ignore[arg-type]
            base_url="http://localhost:11434",
            credential_ref="r",
        )


def test_cloud_protocol_requires_credential() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref=None,
        )


def test_compatible_agents_defaults_by_protocol() -> None:
    # Unset → a credentialed endpoint is offered to every agent; the protocol
    # decides introspection and key handling, not who may be driven by it.
    anthropic = ProviderConfig(protocol="anthropic", base_url="x", credential_ref="r")  # type: ignore[arg-type]
    assert anthropic.compatible_agents is None
    assert anthropic.resolved_compatible_agents() == [
        AgentType.CLAUDE_CODE,
        AgentType.CODEX,
    ]
    openai = ProviderConfig(protocol="openai", base_url="x", credential_ref="r")  # type: ignore[arg-type]
    assert openai.resolved_compatible_agents() == [
        AgentType.CLAUDE_CODE,
        AgentType.CODEX,
    ]
    # unknown is offered to every agent; the user narrows it via checkboxes.
    unknown = ProviderConfig(protocol="unknown", base_url="x", credential_ref="r")  # type: ignore[arg-type]
    assert unknown.resolved_compatible_agents() == [
        AgentType.CLAUDE_CODE,
        AgentType.CODEX,
    ]
    # ollama is internal-only: it projects into no agent.
    ollama = ProviderConfig(protocol="ollama", base_url="http://x")  # type: ignore[arg-type]
    assert ollama.resolved_compatible_agents() == []


def test_compatible_agents_explicit_overrides_default() -> None:
    # The agnes case: an openai-wire endpoint the user routes to Claude Code.
    c = ProviderConfig(
        protocol="openai",  # type: ignore[arg-type]
        base_url="x",
        credential_ref="r",
        compatible_agents=[AgentType.CLAUDE_CODE],
    )
    assert c.resolved_compatible_agents() == [AgentType.CLAUDE_CODE]


def test_compatible_agents_dedupes_preserving_order() -> None:
    c = ProviderConfig(
        protocol="unknown",  # type: ignore[arg-type]
        base_url="x",
        credential_ref="r",
        compatible_agents=[AgentType.CODEX, AgentType.CLAUDE_CODE, AgentType.CODEX],
    )
    assert c.resolved_compatible_agents() == [AgentType.CODEX, AgentType.CLAUDE_CODE]


def test_ollama_cannot_declare_compatible_agents() -> None:
    # ollama has no key and never projects — an explicit agent set is a mistake.
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="ollama",  # type: ignore[arg-type]
            base_url="http://x",
            compatible_agents=[AgentType.CLAUDE_CODE],
        )


def test_bogus_compatible_agent_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="r",
            compatible_agents=["nope"],  # type: ignore[list-item]
        )


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="r",
            bogus=1,
        )


def test_models_defaults_to_unrestricted() -> None:
    # No curated set ⇒ empty ⇒ every model the endpoint serves is on offer.
    c = ProviderConfig(
        protocol="openai",  # type: ignore[arg-type]
        base_url="x",
        credential_ref="r",
    )
    assert c.models == []


def test_models_are_opaque_strings_kept_in_order() -> None:
    # Coffer writes down no model name of its own: whatever the user curated is
    # stored verbatim, in the order they chose, and never checked against a list.
    c = ProviderConfig(
        protocol="unknown",  # type: ignore[arg-type]
        base_url="x",
        credential_ref="r",
        models=["agnes-2.0", "not-a-real-model", "gpt-5"],
    )
    assert c.models == ["agnes-2.0", "not-a-real-model", "gpt-5"]


def test_models_dedupe_and_strip() -> None:
    c = ProviderConfig(
        protocol="openai",  # type: ignore[arg-type]
        base_url="x",
        credential_ref="r",
        models=["gpt-5", " gpt-5 ", "o3"],
    )
    assert c.models == ["gpt-5", "o3"]


def test_blank_model_id_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            protocol="openai",  # type: ignore[arg-type]
            base_url="x",
            credential_ref="r",
            models=["gpt-5", "   "],
        )


def test_absurd_model_ids_rejected() -> None:
    for models in (["m" * 201], [f"m{i}" for i in range(201)]):
        with pytest.raises(ValidationError):
            ProviderConfig(
                protocol="openai",  # type: ignore[arg-type]
                base_url="x",
                credential_ref="r",
                models=models,
            )


def test_ollama_may_curate_models() -> None:
    # ollama projects into no agent, but the internal engine still picks a model
    # from it — so curating that endpoint's list is meaningful.
    c = ProviderConfig(
        protocol="ollama",  # type: ignore[arg-type]
        base_url="http://localhost:11434",
        models=["qwen3:8b"],
    )
    assert c.models == ["qwen3:8b"]

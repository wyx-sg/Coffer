"""BuiltinAgentConfig Pydantic validation + confirmation-policy matching."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coffer.domain.builtin_agent.config import BuiltinAgentConfig


def test_minimal_requires_only_model():
    cfg = BuiltinAgentConfig(model="anthropic:claude-sonnet-4-6")
    assert cfg.model == "anthropic:claude-sonnet-4-6"
    # Defaults: gateway on, no confirmations until opted in, rest unset.
    assert cfg.use_gateway is True
    assert cfg.confirm_tools == []
    assert cfg.system_prompt is None
    assert cfg.temperature is None
    assert cfg.max_tokens is None
    assert cfg.credential_ref is None


def test_empty_model_rejected():
    with pytest.raises(ValidationError):
        BuiltinAgentConfig(model="   ")


def test_temperature_out_of_range_rejected():
    with pytest.raises(ValidationError):
        BuiltinAgentConfig(model="openai:gpt-4o", temperature=5.0)
    with pytest.raises(ValidationError):
        BuiltinAgentConfig(model="openai:gpt-4o", temperature=-0.1)


def test_max_tokens_must_be_positive():
    with pytest.raises(ValidationError):
        BuiltinAgentConfig(model="openai:gpt-4o", max_tokens=0)


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        BuiltinAgentConfig.model_validate({"model": "openai:gpt-4o", "wat": "no"})


def test_requires_confirmation_matches_glob_patterns():
    cfg = BuiltinAgentConfig(model="openai:gpt-4o", confirm_tools=["*delete*", "*write*"])
    assert cfg.requires_confirmation("coffer__delete_memory") is True
    assert cfg.requires_confirmation("fs__write_file") is True
    assert cfg.requires_confirmation("coffer__search_memory") is False


def test_no_confirmation_when_policy_empty():
    cfg = BuiltinAgentConfig(model="openai:gpt-4o")
    assert cfg.requires_confirmation("coffer__delete_memory") is False


def test_json_roundtrip_is_stable():
    cfg = BuiltinAgentConfig(
        model="ollama:llama3",
        system_prompt="be terse",
        temperature=0.2,
        max_tokens=1024,
        credential_ref="builtin/coffer/openai",
        use_gateway=False,
        confirm_tools=["*clear*"],
    )
    dumped = cfg.model_dump(mode="json")
    assert BuiltinAgentConfig.model_validate(dumped) == cfg

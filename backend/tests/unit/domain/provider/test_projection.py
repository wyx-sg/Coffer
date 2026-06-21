"""Pure projection-transform tests (spec 011). No I/O — unit tier."""

from __future__ import annotations

import json
import tomllib

from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import WireFormat
from coffer.domain.provider.projection import (
    ANTHROPIC_API_KEY_HELPER,
    CODEX_ENV_KEY,
    CODEX_PROVIDER_ID,
    apply_anthropic_settings,
    apply_codex_provider,
    target_for,
)


def test_anthropic_sets_managed_keys_and_preserves_others() -> None:
    out = apply_anthropic_settings(
        '{"theme": "dark", "env": {"FOO": "1"}}',
        base_url="https://gw/anthropic",
        model="claude-opus-4-8",
        fast_model="claude-haiku-4-5",
    )
    d = json.loads(out)
    assert d["apiKeyHelper"] == ANTHROPIC_API_KEY_HELPER
    assert d["theme"] == "dark"  # unrelated key preserved
    assert d["env"]["FOO"] == "1"  # unrelated env preserved
    assert d["env"]["ANTHROPIC_BASE_URL"] == "https://gw/anthropic"
    assert d["env"]["ANTHROPIC_MODEL"] == "claude-opus-4-8"
    assert d["env"]["ANTHROPIC_SMALL_FAST_MODEL"] == "claude-haiku-4-5"
    assert "ANTHROPIC_API_KEY" not in d["env"]  # never write the raw key


def test_anthropic_omits_fast_model_when_none() -> None:
    out = apply_anthropic_settings(
        '{"env": {"ANTHROPIC_SMALL_FAST_MODEL": "stale"}}',
        base_url="u",
        model="m",
        fast_model=None,
    )
    assert "ANTHROPIC_SMALL_FAST_MODEL" not in json.loads(out)["env"]


def test_anthropic_handles_empty_and_is_idempotent() -> None:
    first = apply_anthropic_settings("", base_url="u", model="m", fast_model="f")
    assert json.loads(first)["env"]["ANTHROPIC_BASE_URL"] == "u"
    second = apply_anthropic_settings(first, base_url="u", model="m", fast_model="f")
    assert json.loads(first) == json.loads(second)


def test_codex_sets_provider_block_and_preserves_others() -> None:
    out = apply_codex_provider(
        'approval_policy = "never"\n',
        base_url="https://gw/v1",
        model="gpt-x",
        wire_api="chat",
        display_name="Coffer (acme)",
    )
    doc = tomllib.loads(out)
    assert doc["approval_policy"] == "never"  # unrelated key preserved
    assert doc["model"] == "gpt-x"
    assert doc["model_provider"] == CODEX_PROVIDER_ID
    block = doc["model_providers"][CODEX_PROVIDER_ID]
    assert block["base_url"] == "https://gw/v1"
    assert block["wire_api"] == "chat"
    assert block["env_key"] == CODEX_ENV_KEY
    assert block["name"] == "Coffer (acme)"


def test_codex_handles_empty_and_is_idempotent() -> None:
    first = apply_codex_provider("", base_url="u", model="m", wire_api="chat", display_name="x")
    second = apply_codex_provider(first, base_url="u", model="m", wire_api="chat", display_name="x")
    assert tomllib.loads(first) == tomllib.loads(second)


def test_targets_map_wire_to_agent() -> None:
    assert target_for(WireFormat.ANTHROPIC).agent_type is AgentType.CLAUDE_CODE
    assert target_for(WireFormat.ANTHROPIC).config_key == "settings"
    assert target_for(WireFormat.OPENAI).agent_type is AgentType.CODEX
    assert target_for(WireFormat.OPENAI).config_key == "config"

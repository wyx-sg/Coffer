"""Pure projection-transform tests (spec 011). No I/O — unit tier."""

from __future__ import annotations

import json
import tomllib

from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import Protocol
from coffer.domain.provider.projection import (
    ANTHROPIC_API_KEY_HELPER,
    CODEX_ENV_KEY,
    CODEX_PROVIDER_ID,
    apply_anthropic_settings,
    apply_codex_provider,
    remove_anthropic_settings,
    remove_codex_provider,
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


# --- de-projection (use-built-in: remove Coffer's managed keys) ----------------


def test_remove_anthropic_clears_managed_keys_preserves_others() -> None:
    text = apply_anthropic_settings(
        '{"theme": "dark", "env": {"FOO": "1"}}',
        base_url="u",
        model="m",
        fast_model="f",
    )
    d = json.loads(remove_anthropic_settings(text))
    assert "apiKeyHelper" not in d  # Coffer's managed helper removed
    assert d["theme"] == "dark"  # unrelated key preserved
    assert d["env"]["FOO"] == "1"  # unrelated env preserved
    for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL"):
        assert k not in d["env"]


def test_remove_anthropic_keeps_a_user_owned_apikeyhelper() -> None:
    d = json.loads(
        remove_anthropic_settings(
            '{"apiKeyHelper": "my-own-helper", "env": {"ANTHROPIC_BASE_URL": "u"}}'
        )
    )
    assert d["apiKeyHelper"] == "my-own-helper"  # only Coffer's managed helper is cleared
    assert "ANTHROPIC_BASE_URL" not in d["env"]


def test_remove_anthropic_empty_and_idempotent() -> None:
    assert json.loads(remove_anthropic_settings("")) == {}
    once = remove_anthropic_settings(
        apply_anthropic_settings("", base_url="u", model="m", fast_model=None)
    )
    twice = remove_anthropic_settings(once)
    assert json.loads(once) == json.loads(twice)


def test_remove_codex_clears_managed_block_preserves_others() -> None:
    text = apply_codex_provider(
        'approval_policy = "never"\n',
        base_url="u",
        model="gpt-x",
        wire_api="responses",
        display_name="Coffer (acme)",
    )
    doc = tomllib.loads(remove_codex_provider(text))
    assert doc["approval_policy"] == "never"  # unrelated key preserved
    assert "model_provider" not in doc  # Coffer selector removed
    assert "model" not in doc  # Coffer-projected model removed → codex default
    assert CODEX_PROVIDER_ID not in doc.get("model_providers", {})


def test_remove_codex_keeps_a_user_owned_provider() -> None:
    doc = tomllib.loads(
        remove_codex_provider(
            'model_provider = "myown"\nmodel = "x"\n\n[model_providers.myown]\nbase_url = "u"\n'
        )
    )
    # A non-Coffer active provider is left untouched (we only undo our own).
    assert doc["model_provider"] == "myown"
    assert doc["model"] == "x"
    assert "myown" in doc["model_providers"]


def test_remove_codex_empty_and_idempotent() -> None:
    assert remove_codex_provider("").strip() == ""
    once = remove_codex_provider(
        apply_codex_provider("", base_url="u", model="m", wire_api="responses", display_name="x")
    )
    twice = remove_codex_provider(once)
    assert tomllib.loads(once) == tomllib.loads(twice)


def test_targets_map_wire_to_agent() -> None:
    assert target_for(Protocol.ANTHROPIC).agent_type is AgentType.CLAUDE_CODE
    assert target_for(Protocol.ANTHROPIC).config_key == "settings"
    assert target_for(Protocol.OPENAI).agent_type is AgentType.CODEX
    assert target_for(Protocol.OPENAI).config_key == "config"

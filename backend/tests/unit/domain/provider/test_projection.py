"""Pure projection-transform tests (spec provider-switching). No I/O — unit tier."""

from __future__ import annotations

import json
import pathlib
import tomllib

import pytest

from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import Protocol
from coffer.domain.provider.projection import (
    ANTHROPIC_API_KEY_HELPER,
    CODEX_ENV_KEY,
    CODEX_PROVIDER_ID,
    anthropic_api_key_helper,
    apply_anthropic_settings,
    apply_codex_provider,
    codex_model_catalog_json,
    codex_model_catalog_path,
    remove_anthropic_settings,
    remove_codex_provider,
    target_for,
    target_for_agent,
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


def test_target_for_agent_maps_agent_to_config() -> None:
    # The projection writer is now chosen by AGENT type, not protocol — so an
    # openai-wire connection routed to Claude Code writes settings.json.
    cc = target_for_agent(AgentType.CLAUDE_CODE)
    assert cc is not None and cc.config_key == "settings"
    cx = target_for_agent(AgentType.CODEX)
    assert cx is not None and cx.config_key == "config"


def test_per_connection_api_key_helper_is_written_and_removed() -> None:
    helper = anthropic_api_key_helper("agnes")
    assert helper == "coffer provider key --connection agnes"
    out = apply_anthropic_settings(
        "", base_url="https://agnes", model=None, fast_model=None, api_key_helper=helper
    )
    assert json.loads(out)["apiKeyHelper"] == helper
    # Removal strips ANY Coffer-managed helper by prefix (per-connection or the
    # legacy --wire form), so use-builtin always reverts cleanly.
    assert "apiKeyHelper" not in json.loads(remove_anthropic_settings(out))
    legacy = '{"apiKeyHelper": "coffer provider key --wire anthropic"}'
    assert "apiKeyHelper" not in json.loads(remove_anthropic_settings(legacy))


# --- supported-agent invariant -------------------------------------------------


# Coffer supports exactly the agent types it can project a provider into: every
# member of ``AgentType`` MUST have a native-config projection target. This locks
# the invariant so a newly added agent type cannot silently ship without a
# projection writer (and so a removed one cannot leave a dangling target).
@pytest.mark.parametrize("agent_type", list(AgentType))
def test_every_supported_agent_is_a_projection_target(agent_type: AgentType) -> None:
    assert target_for_agent(agent_type) is not None


# --- Codex model catalogue (``model_catalog_json``) -----------------------------

# The catalogue file is a WIRE CONTRACT with another program: Codex's parser
# rejects the document if any of these is missing, and then falls back to its
# built-in model list — so the projection silently does not take effect. Verified
# against Codex 0.139.0.
_REQUIRED_CATALOG_FIELDS = {
    "slug",
    "display_name",
    "supported_reasoning_levels",
    "shell_type",
    "visibility",
    "supported_in_api",
    "priority",
    "base_instructions",
    "supports_reasoning_summaries",
    "support_verbosity",
    "truncation_policy",
    "supports_parallel_tool_calls",
    "experimental_supported_tools",
}


def test_catalog_emits_exactly_the_fields_codex_requires() -> None:
    text = codex_model_catalog_json(["m-one", "m-two"])
    assert text is not None
    doc = json.loads(text)
    assert set(doc) == {"models"}
    for entry in doc["models"]:
        assert set(entry) == _REQUIRED_CATALOG_FIELDS


def test_catalog_describes_each_curated_model_in_curated_order() -> None:
    text = codex_model_catalog_json(["fast", "pro"])
    assert text is not None
    models = json.loads(text)["models"]
    assert [m["slug"] for m in models] == ["fast", "pro"]
    # The id is the display name — Coffer authors no model labels of its own.
    assert [m["display_name"] for m in models] == ["fast", "pro"]
    # Codex orders by ascending priority, so the curated order is the index.
    assert [m["priority"] for m in models] == [0, 1]


def test_catalog_claims_only_what_coffer_can_know() -> None:
    text = codex_model_catalog_json(["m"])
    assert text is not None
    entry = json.loads(text)["models"][0]
    assert entry["visibility"] == "list"  # the point is to appear in the picker
    assert entry["supported_in_api"] is True  # curated for an API endpoint
    # Capabilities Coffer cannot derive for a third-party endpoint claim nothing,
    # so Codex sends no reasoning/verbosity/parallel-tool parameters for them.
    assert entry["supported_reasoning_levels"] == []
    assert entry["supports_reasoning_summaries"] is False
    assert entry["support_verbosity"] is False
    assert entry["supports_parallel_tool_calls"] is False
    assert entry["experimental_supported_tools"] == []
    assert entry["shell_type"] == "default"
    assert entry["base_instructions"] == ""
    # Tool-output truncation is a property of Codex's harness, not the endpoint,
    # so it mirrors the built-in catalogue rather than guessing a context window.
    assert entry["truncation_policy"] == {"mode": "tokens", "limit": 10000}


def test_no_catalog_without_a_curated_model_set() -> None:
    # An empty set means "no restriction". A catalogue REPLACES Codex's built-in
    # list, so writing one here would replace it with a guess.
    assert codex_model_catalog_json([]) is None


def test_catalog_path_sits_next_to_config_toml() -> None:
    assert codex_model_catalog_path(pathlib.Path("/home/u/.codex")) == pathlib.Path(
        "/home/u/.codex/coffer-model-catalog.json"
    )


def test_codex_points_at_an_absolute_catalog_path() -> None:
    out = apply_codex_provider(
        "",
        base_url="u",
        model="m",
        wire_api="responses",
        display_name="x",
        catalog_path=pathlib.Path("/home/u/.codex/coffer-model-catalog.json"),
    )
    value = tomllib.loads(out)["model_catalog_json"]
    assert value == "/home/u/.codex/coffer-model-catalog.json"
    assert pathlib.PurePosixPath(value).is_absolute()


def test_codex_rejects_a_relative_catalog_path() -> None:
    # Codex resolves the key as an absolute path; a relative one would resolve
    # against whatever cwd the agent happened to start in.
    with pytest.raises(ValueError, match="must be absolute"):
        apply_codex_provider(
            "",
            base_url="u",
            model="m",
            wire_api="responses",
            display_name="x",
            catalog_path=pathlib.Path(".codex/coffer-model-catalog.json"),
        )


def test_codex_drops_a_stale_coffer_catalog_when_the_set_is_cleared() -> None:
    projected = apply_codex_provider(
        "",
        base_url="u",
        model="m",
        wire_api="responses",
        display_name="x",
        catalog_path=pathlib.Path("/home/u/.codex/coffer-model-catalog.json"),
    )
    cleared = apply_codex_provider(
        projected, base_url="u", model="m", wire_api="responses", display_name="x"
    )
    assert "model_catalog_json" not in tomllib.loads(cleared)


def test_codex_keeps_a_user_owned_catalog_when_it_curates_nothing() -> None:
    out = apply_codex_provider(
        'model_catalog_json = "/home/u/my-models.json"\n',
        base_url="u",
        model="m",
        wire_api="responses",
        display_name="x",
    )
    assert tomllib.loads(out)["model_catalog_json"] == "/home/u/my-models.json"


def test_remove_codex_drops_the_coffer_catalog() -> None:
    text = apply_codex_provider(
        "",
        base_url="u",
        model="m",
        wire_api="responses",
        display_name="x",
        catalog_path=pathlib.Path("/home/u/.codex/coffer-model-catalog.json"),
    )
    # Gone → Codex's own model list is what its picker shows again.
    assert "model_catalog_json" not in tomllib.loads(remove_codex_provider(text))


def test_remove_codex_keeps_a_user_owned_catalog() -> None:
    # Matched by the Coffer-owned filename, exactly as ``apiKeyHelper`` is matched
    # by its managed prefix: a catalogue the user wrote is never removed.
    doc = tomllib.loads(
        remove_codex_provider('model_catalog_json = "/home/u/catalog.json"\napproval = "never"\n')
    )
    assert doc["model_catalog_json"] == "/home/u/catalog.json"
    assert doc["approval"] == "never"


def test_catalog_projection_preserves_comments_and_ordering() -> None:
    original = '# my codex config\napproval_policy = "never"\nsandbox_mode = "read-only"\n'
    out = apply_codex_provider(
        original,
        base_url="u",
        model="m",
        wire_api="responses",
        display_name="x",
        catalog_path=pathlib.Path("/home/u/.codex/coffer-model-catalog.json"),
    )
    assert out.startswith(
        '# my codex config\napproval_policy = "never"\nsandbox_mode = "read-only"'
    )
    reverted = remove_codex_provider(out)
    # Round-trip leaves the user's file as it was, down to the comment (tomlkit's
    # re-serialisation leaves the blank line the removed table stood on).
    assert reverted.strip() == original.strip()

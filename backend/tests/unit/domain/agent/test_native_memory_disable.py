"""Unit tests for the native-memory disable/restore transforms (Slice 6).

Claude Code (JSON ``settings.json``) toggles ``autoMemoryEnabled``; Codex (TOML
``config.toml``) toggles ``features.memories`` + ``memories.generate_memories``.
Pure text transforms; idempotent; preserve unrelated content (and TOML comments).
"""

from __future__ import annotations

import json

import tomlkit

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.native_memory_disable import (
    apply_disable,
    apply_restore,
    is_disabled,
)
from coffer.domain.agent.types import AgentType

_JSON = ConfigFileFormat.JSON
_TOML = ConfigFileFormat.TOML


# --- Claude Code (JSON) -------------------------------------------------------


def test_claude_disable_sets_flag_false() -> None:
    out = apply_disable("", fmt=_JSON, agent_type=AgentType.CLAUDE_CODE)
    assert json.loads(out)["autoMemoryEnabled"] is False
    assert is_disabled(out, fmt=_JSON, agent_type=AgentType.CLAUDE_CODE) is True


def test_claude_disable_preserves_unrelated_keys() -> None:
    seed = json.dumps({"model": "claude-opus-4", "autoMemoryEnabled": True})
    out = apply_disable(seed, fmt=_JSON, agent_type=AgentType.CLAUDE_CODE)
    data = json.loads(out)
    assert data["model"] == "claude-opus-4"
    assert data["autoMemoryEnabled"] is False


def test_claude_restore_removes_flag() -> None:
    disabled = apply_disable(
        json.dumps({"model": "x"}), fmt=_JSON, agent_type=AgentType.CLAUDE_CODE
    )
    out = apply_restore(disabled, fmt=_JSON, agent_type=AgentType.CLAUDE_CODE)
    data = json.loads(out)
    assert "autoMemoryEnabled" not in data
    assert data["model"] == "x"
    assert is_disabled(out, fmt=_JSON, agent_type=AgentType.CLAUDE_CODE) is False


def test_claude_disable_is_idempotent() -> None:
    once = apply_disable("", fmt=_JSON, agent_type=AgentType.CLAUDE_CODE)
    twice = apply_disable(once, fmt=_JSON, agent_type=AgentType.CLAUDE_CODE)
    assert json.loads(once) == json.loads(twice)


def test_claude_is_disabled_false_when_flag_true() -> None:
    seed = json.dumps({"autoMemoryEnabled": True})
    assert is_disabled(seed, fmt=_JSON, agent_type=AgentType.CLAUDE_CODE) is False
    assert is_disabled("", fmt=_JSON, agent_type=AgentType.CLAUDE_CODE) is False


# --- Codex (TOML) -------------------------------------------------------------


def test_codex_disable_sets_both_flags_false() -> None:
    out = apply_disable("", fmt=_TOML, agent_type=AgentType.CODEX)
    doc = tomlkit.parse(out)
    assert doc["features"]["memories"] is False
    assert doc["memories"]["generate_memories"] is False
    assert is_disabled(out, fmt=_TOML, agent_type=AgentType.CODEX) is True


def test_codex_disable_preserves_comments_and_unrelated() -> None:
    seed = '# my codex config\nmodel = "gpt-5"\n\n[features]\nweb_search = true\n'
    out = apply_disable(seed, fmt=_TOML, agent_type=AgentType.CODEX)
    assert "# my codex config" in out
    doc = tomlkit.parse(out)
    assert doc["model"] == "gpt-5"
    assert doc["features"]["web_search"] is True
    assert doc["features"]["memories"] is False


def test_codex_restore_removes_keys() -> None:
    disabled = apply_disable('model = "gpt-5"\n', fmt=_TOML, agent_type=AgentType.CODEX)
    out = apply_restore(disabled, fmt=_TOML, agent_type=AgentType.CODEX)
    assert is_disabled(out, fmt=_TOML, agent_type=AgentType.CODEX) is False
    doc = tomlkit.parse(out)
    assert doc["model"] == "gpt-5"
    # the keys we added are gone
    features = doc.get("features")
    assert features is None or "memories" not in features
    memories = doc.get("memories")
    assert memories is None or "generate_memories" not in memories


def test_codex_disable_is_idempotent() -> None:
    once = apply_disable("", fmt=_TOML, agent_type=AgentType.CODEX)
    twice = apply_disable(once, fmt=_TOML, agent_type=AgentType.CODEX)
    assert tomlkit.parse(once) == tomlkit.parse(twice)


def test_codex_is_disabled_false_when_only_one_flag() -> None:
    seed = "[features]\nmemories = false\n"
    assert is_disabled(seed, fmt=_TOML, agent_type=AgentType.CODEX) is False


# --- Hermes (YAML config.yaml, memory.memory_enabled/user_profile_enabled) -----

_YAML = ConfigFileFormat.YAML


def test_hermes_disable_sets_both_flags_and_preserves_others() -> None:
    import yaml

    seed = "memory:\n  memory_char_limit: 5000\n"
    out = apply_disable(seed, fmt=_YAML, agent_type=AgentType.HERMES)
    d = yaml.safe_load(out)
    assert d["memory"]["memory_char_limit"] == 5000  # unrelated memory setting kept
    assert d["memory"]["memory_enabled"] is False
    assert d["memory"]["user_profile_enabled"] is False
    assert is_disabled(out, fmt=_YAML, agent_type=AgentType.HERMES) is True


def test_hermes_restore_removes_only_coffer_keys() -> None:
    import yaml

    disabled = apply_disable(
        "memory:\n  memory_char_limit: 5000\n", fmt=_YAML, agent_type=AgentType.HERMES
    )
    restored = apply_restore(disabled, fmt=_YAML, agent_type=AgentType.HERMES)
    d = yaml.safe_load(restored)
    assert d["memory"]["memory_char_limit"] == 5000  # kept
    assert "memory_enabled" not in d["memory"]
    assert "user_profile_enabled" not in d["memory"]
    assert is_disabled(restored, fmt=_YAML, agent_type=AgentType.HERMES) is False


def test_hermes_disable_is_idempotent() -> None:
    once = apply_disable("", fmt=_YAML, agent_type=AgentType.HERMES)
    twice = apply_disable(once, fmt=_YAML, agent_type=AgentType.HERMES)
    assert once == twice


def test_hermes_is_disabled_false_when_only_one_flag() -> None:
    seed = "memory:\n  memory_enabled: false\n"
    assert is_disabled(seed, fmt=_YAML, agent_type=AgentType.HERMES) is False


def test_hermes_restore_drops_a_memory_block_coffer_created() -> None:
    import yaml

    # No prior memory block → disable creates it → restore removes it entirely
    # (rather than leaving an empty `memory: {}`).
    disabled = apply_disable("model:\n  provider: x\n", fmt=_YAML, agent_type=AgentType.HERMES)
    restored = apply_restore(disabled, fmt=_YAML, agent_type=AgentType.HERMES)
    d = yaml.safe_load(restored)
    assert "memory" not in d
    assert d["model"]["provider"] == "x"  # unrelated content preserved


# --- openclaw (JSON plugins.slots.memory, ADR-044) ------------------------------


def test_openclaw_disable_empties_the_memory_slot() -> None:
    out = apply_disable("", fmt=_JSON, agent_type=AgentType.OPENCLAW)
    assert json.loads(out)["plugins"]["slots"]["memory"] == "none"
    assert is_disabled(out, fmt=_JSON, agent_type=AgentType.OPENCLAW) is True


def test_openclaw_disable_preserves_unrelated_keys_and_plugin_entries() -> None:
    seed = json.dumps(
        {
            "gateway": {"port": 18789},
            "plugins": {"entries": {"coffer-session-context": {"enabled": True}}},
        }
    )
    data = json.loads(apply_disable(seed, fmt=_JSON, agent_type=AgentType.OPENCLAW))
    assert data["gateway"] == {"port": 18789}
    assert data["plugins"]["entries"]["coffer-session-context"] == {"enabled": True}
    assert data["plugins"]["slots"] == {"memory": "none"}


def test_openclaw_restore_removes_only_coffer_slot() -> None:
    seed = json.dumps({"plugins": {"slots": {"memory": "none", "voice": "x"}}})
    data = json.loads(apply_restore(seed, fmt=_JSON, agent_type=AgentType.OPENCLAW))
    # An unrelated slot keeps the block alive; only the memory key goes.
    assert data["plugins"]["slots"] == {"voice": "x"}


def test_openclaw_restore_drops_containers_coffer_created() -> None:
    disabled = apply_disable("", fmt=_JSON, agent_type=AgentType.OPENCLAW)
    out = apply_restore(disabled, fmt=_JSON, agent_type=AgentType.OPENCLAW)
    assert json.loads(out) == {}
    assert is_disabled(out, fmt=_JSON, agent_type=AgentType.OPENCLAW) is False


def test_openclaw_disable_is_idempotent() -> None:
    once = apply_disable("", fmt=_JSON, agent_type=AgentType.OPENCLAW)
    twice = apply_disable(once, fmt=_JSON, agent_type=AgentType.OPENCLAW)
    assert json.loads(once) == json.loads(twice)


def test_openclaw_is_disabled_false_for_other_slot_values() -> None:
    seed = json.dumps({"plugins": {"slots": {"memory": "memory-core"}}})
    assert is_disabled(seed, fmt=_JSON, agent_type=AgentType.OPENCLAW) is False

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

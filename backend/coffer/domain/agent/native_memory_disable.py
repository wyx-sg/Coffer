"""Disable / restore an agent's *native* write-side memory (Slice 6).

Coffer is the shared memory store across an agent's tools; the opt-in
``disable_native_memory`` toggle stops the agent from also writing to its own
native memory (it does NOT stop it reading instruction files like CLAUDE.md).

Pure domain text transforms — no filesystem access. Two backends:

- **Claude Code** (JSON ``settings.json``): ``autoMemoryEnabled = false``.
- **Codex** (TOML ``config.toml``): ``features.memories = false`` +
  ``memories.generate_memories = false`` (tomlkit preserves comments/ordering).

``apply_disable`` sets the flag(s); ``apply_restore`` removes the key(s) Coffer
added; ``is_disabled`` reports whether the disable is in effect. All idempotent.
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any

import tomlkit

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.mcp_entries import _parse_json, _parse_toml
from coffer.domain.agent.types import AgentType

#: Claude Code JSON key.
_CLAUDE_KEY = "autoMemoryEnabled"


def _is_json(fmt: ConfigFileFormat, agent_type: AgentType) -> bool:
    """JSON (Claude Code) backend vs TOML (Codex) backend.

    Dispatch is by agent type, with ``fmt`` carried so callers can pass the
    descriptor format directly; the two always agree for current agents.
    """
    if agent_type is AgentType.CLAUDE_CODE:
        return True
    if agent_type is AgentType.CODEX:
        return False
    raise AssertionError(  # pragma: no cover - every enum value handled
        f"native-memory disable unsupported for agent {agent_type!r}"
    )


def _dump_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def apply_disable(content: str, *, fmt: ConfigFileFormat, agent_type: AgentType) -> str:
    """Return new config text with native write-side memory disabled."""
    if _is_json(fmt, agent_type):
        data = _parse_json(content)
        data[_CLAUDE_KEY] = False
        return _dump_json(data)

    doc = _parse_toml(content)
    if not isinstance(doc.get("features"), MutableMapping):
        doc["features"] = tomlkit.table()
    doc["features"]["memories"] = False
    if not isinstance(doc.get("memories"), MutableMapping):
        doc["memories"] = tomlkit.table()
    doc["memories"]["generate_memories"] = False
    return tomlkit.dumps(doc)


def apply_restore(content: str, *, fmt: ConfigFileFormat, agent_type: AgentType) -> str:
    """Return new config text with the disable removed (restore native memory)."""
    if _is_json(fmt, agent_type):
        data = _parse_json(content)
        data.pop(_CLAUDE_KEY, None)
        return _dump_json(data)

    doc = _parse_toml(content)
    features = doc.get("features")
    if isinstance(features, MutableMapping) and "memories" in features:
        del features["memories"]
    memories = doc.get("memories")
    if isinstance(memories, MutableMapping) and "generate_memories" in memories:
        del memories["generate_memories"]
    return tomlkit.dumps(doc)


def is_disabled(content: str, *, fmt: ConfigFileFormat, agent_type: AgentType) -> bool:
    """Whether native write-side memory is currently disabled in ``content``."""
    if not content.strip():
        return False
    if _is_json(fmt, agent_type):
        return _parse_json(content).get(_CLAUDE_KEY) is False

    doc = _parse_toml(content)
    features = doc.get("features")
    memories = doc.get("memories")
    features_off = isinstance(features, MutableMapping) and features.get("memories") is False
    generate_off = (
        isinstance(memories, MutableMapping) and memories.get("generate_memories") is False
    )
    return features_off and generate_off

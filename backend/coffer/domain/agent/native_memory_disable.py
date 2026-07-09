"""Disable / restore an agent's *native* write-side memory (Slice 6).

Coffer is the shared memory store across an agent's tools; the opt-in
``disable_native_memory`` toggle stops the agent from also writing to its own
native memory (it does NOT stop it reading instruction files like CLAUDE.md).

Pure domain text transforms — no filesystem access. Three backends:

- **Claude Code** (JSON ``settings.json``): ``autoMemoryEnabled = false``.
- **Codex** (TOML ``config.toml``): ``features.memories = false`` +
  ``memories.generate_memories = false`` (tomlkit preserves comments/ordering).
- **Hermes** (YAML ``config.yaml``): ``memory.memory_enabled = false`` +
  ``memory.user_profile_enabled = false`` (ruamel preserves comments/ordering).
- **openclaw** (JSON ``openclaw.json``): ``plugins.slots.memory = "none"``
  (empties the memory plugin slot — probe-validated on 2026.6.11; ADR-044).

``apply_disable`` sets the flag(s); ``apply_restore`` removes the key(s) Coffer
added; ``is_disabled`` reports whether the disable is in effect. All idempotent.
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any

import tomlkit

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.mcp_entries import _dump_yaml, _parse_json, _parse_toml, _parse_yaml
from coffer.domain.agent.types import AgentType

#: Claude Code JSON key.
_CLAUDE_KEY = "autoMemoryEnabled"
#: Hermes YAML ``memory`` sub-keys Coffer flips off.
_HERMES_MEMORY_KEYS = ("memory_enabled", "user_profile_enabled")
#: openclaw ``plugins.slots.memory`` value that empties the memory slot.
_OPENCLAW_SLOT_OFF = "none"


def _is_json(fmt: ConfigFileFormat, agent_type: AgentType) -> bool:
    """JSON (Claude Code) backend vs TOML (Codex) backend. YAML (Hermes) and
    the openclaw JSON slot are handled by their own branches before this is
    called."""
    if agent_type is AgentType.CLAUDE_CODE:
        return True
    if agent_type is AgentType.CODEX:
        return False
    raise AssertionError(  # pragma: no cover - every enum value handled
        f"native-memory disable unsupported for agent {agent_type!r}"
    )


def _dump_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _yaml_memory_block(doc: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Return the ``memory`` mapping, creating it if absent/non-mapping."""
    mem = doc.get("memory")
    if not isinstance(mem, MutableMapping):
        mem = {}
        doc["memory"] = mem
    return mem


def _openclaw_slots(doc: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Return the ``plugins.slots`` mapping, creating steps if absent/non-mapping."""
    plugins = doc.get("plugins")
    if not isinstance(plugins, MutableMapping):
        plugins = {}
        doc["plugins"] = plugins
    slots = plugins.get("slots")
    if not isinstance(slots, MutableMapping):
        slots = {}
        plugins["slots"] = slots
    return slots


def apply_disable(content: str, *, fmt: ConfigFileFormat, agent_type: AgentType) -> str:
    """Return new config text with native write-side memory disabled."""
    if agent_type is AgentType.OPENCLAW:
        doc_json = _parse_json(content)
        _openclaw_slots(doc_json)["memory"] = _OPENCLAW_SLOT_OFF
        return _dump_json(doc_json)

    if fmt is ConfigFileFormat.YAML:
        doc = _parse_yaml(content)
        mem = _yaml_memory_block(doc)
        for key in _HERMES_MEMORY_KEYS:
            mem[key] = False
        return _dump_yaml(doc)

    if _is_json(fmt, agent_type):
        data = _parse_json(content)
        data[_CLAUDE_KEY] = False
        return _dump_json(data)

    doc_toml = _parse_toml(content)
    if not isinstance(doc_toml.get("features"), MutableMapping):
        doc_toml["features"] = tomlkit.table()
    doc_toml["features"]["memories"] = False
    if not isinstance(doc_toml.get("memories"), MutableMapping):
        doc_toml["memories"] = tomlkit.table()
    doc_toml["memories"]["generate_memories"] = False
    return tomlkit.dumps(doc_toml)


def apply_restore(content: str, *, fmt: ConfigFileFormat, agent_type: AgentType) -> str:
    """Return new config text with the disable removed (restore native memory).

    Only the key(s) Coffer added are removed; unrelated ``memory`` settings (e.g.
    ``memory_char_limit``) are left untouched.
    """
    if agent_type is AgentType.OPENCLAW:
        doc_json = _parse_json(content)
        plugins = doc_json.get("plugins")
        if isinstance(plugins, MutableMapping):
            slots = plugins.get("slots")
            if isinstance(slots, MutableMapping):
                slots.pop("memory", None)
                if not slots:  # drop a block we created that is now empty
                    plugins.pop("slots", None)
            # `plugins` also carries `entries` (the FR-048 extension flag), so it
            # is only dropped when the slot removal left it fully empty.
            if not plugins:
                doc_json.pop("plugins", None)
        return _dump_json(doc_json)

    if fmt is ConfigFileFormat.YAML:
        doc = _parse_yaml(content)
        mem = doc.get("memory")
        if isinstance(mem, MutableMapping):
            for key in _HERMES_MEMORY_KEYS:
                if key in mem:
                    del mem[key]
            if not mem:  # drop a block we created that is now empty (stay tidy)
                doc.pop("memory", None)
        return _dump_yaml(doc)

    if _is_json(fmt, agent_type):
        data = _parse_json(content)
        data.pop(_CLAUDE_KEY, None)
        return _dump_json(data)

    doc_toml = _parse_toml(content)
    features = doc_toml.get("features")
    if isinstance(features, MutableMapping) and "memories" in features:
        del features["memories"]
    memories = doc_toml.get("memories")
    if isinstance(memories, MutableMapping) and "generate_memories" in memories:
        del memories["generate_memories"]
    return tomlkit.dumps(doc_toml)


def is_disabled(content: str, *, fmt: ConfigFileFormat, agent_type: AgentType) -> bool:
    """Whether native write-side memory is currently disabled in ``content``."""
    if not content.strip():
        return False
    if agent_type is AgentType.OPENCLAW:
        plugins = _parse_json(content).get("plugins")
        if not isinstance(plugins, MutableMapping):
            return False
        slots = plugins.get("slots")
        return isinstance(slots, MutableMapping) and slots.get("memory") == _OPENCLAW_SLOT_OFF
    if fmt is ConfigFileFormat.YAML:
        doc = _parse_yaml(content)
        mem = doc.get("memory")
        if not isinstance(mem, MutableMapping):
            return False
        return all(mem.get(key) is False for key in _HERMES_MEMORY_KEYS)

    if _is_json(fmt, agent_type):
        return _parse_json(content).get(_CLAUDE_KEY) is False

    doc_toml = _parse_toml(content)
    features = doc_toml.get("features")
    memories = doc_toml.get("memories")
    features_off = isinstance(features, MutableMapping) and features.get("memories") is False
    generate_off = (
        isinstance(memories, MutableMapping) and memories.get("generate_memories") is False
    )
    return features_off and generate_off

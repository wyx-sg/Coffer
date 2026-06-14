"""Plugin text transforms for Cursor, OpenCode, and OpenClaw.

Pure domain transforms — no filesystem access. Split from ``plugin_state.py``
(which holds the Claude Code and Codex transforms) to keep each file under the
backend file-size limit. The value objects (:class:`PluginInfo`,
:class:`MarketplaceInfo`) and the shared ``_safe_parse_json`` helper live in
``plugin_state.py`` and are imported here.

Per-agent model:
- **Cursor** — read-only. Lists VSIX extensions from ``extensions.json`` (a JSON
  array); enable/disable lives in Cursor's SQLite (internal state), so every
  listed extension is reported enabled and there is no toggle/uninstall here.
- **OpenCode** — toggle = membership in the top-level ``plugin`` array of
  ``opencode.json``; uninstall = removal from that array.
- **OpenClaw** — the ``plugins`` block of ``openclaw.json``. The schema is only
  partly documented, so reads are tolerant: ``entries`` enumerates ids,
  ``enabled``/``allow`` are allow-lists, ``deny`` is a deny-list.
"""

from __future__ import annotations

import json
from typing import Any

from coffer.domain.agent.plugin_state import (
    MarketplaceInfo,
    PluginInfo,
    _safe_parse_json,
)
from coffer.domain.workspace_errors import AgentConfigParseError, PluginNotFound

# ---------------------------------------------------------------------------
# Cursor (read-only)
# ---------------------------------------------------------------------------


def _safe_parse_json_value(text: str | None) -> Any:
    """Parse JSON text to any top-level value; ``None``/empty → ``None``.

    Unlike ``_safe_parse_json``, this does not require a top-level object —
    Cursor's ``extensions.json`` is a top-level JSON array.
    """
    if not text or not text.strip():
        return None
    try:
        return json.loads(text)
    except ValueError as e:
        raise AgentConfigParseError("<config>", str(e)) from e


def parse_cursor(extensions_json: str | None) -> tuple[list[PluginInfo], list[MarketplaceInfo]]:
    """Parse Cursor's ``~/.cursor/extensions/extensions.json`` (read-only).

    The file is a JSON array of ``{"identifier": {"id": ...}, "version": ...}``
    objects. Enable/disable state lives in Cursor's SQLite (internal state) so
    every listed extension is reported ``enabled``. There is no marketplace
    concept here, so the marketplace list is always empty.

    Raises ``AgentConfigParseError`` on malformed JSON. A non-array top level is
    tolerated as "no extensions".
    """
    data = _safe_parse_json_value(extensions_json)
    plugins: list[PluginInfo] = []
    if isinstance(data, list):
        for raw in data:
            if not isinstance(raw, dict):
                continue
            identifier = raw.get("identifier")
            ext_id = identifier.get("id") if isinstance(identifier, dict) else None
            if not isinstance(ext_id, str) or not ext_id:
                continue
            plugins.append(PluginInfo(id=ext_id, name=ext_id, marketplace="", enabled=True))
    return plugins, []


# ---------------------------------------------------------------------------
# OpenCode (the "plugin" array in opencode.json)
# ---------------------------------------------------------------------------


def _opencode_plugin_list(data: dict[str, Any]) -> list[str]:
    raw = data.get("plugin")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if isinstance(item, str)]


def parse_opencode(config_json: str | None) -> tuple[list[PluginInfo], list[MarketplaceInfo]]:
    """Parse OpenCode plugin state from ``opencode.json``.

    Plugins are the strings (names or local paths) in the top-level ``plugin``
    array. Presence in the array means enabled; OpenCode has no per-plugin
    disabled flag and no marketplace concept.

    Raises ``AgentConfigParseError`` on malformed JSON.
    """
    data = _safe_parse_json(config_json)
    plugins = [
        PluginInfo(id=item, name=item, marketplace="", enabled=True)
        for item in _opencode_plugin_list(data)
    ]
    return plugins, []


def set_opencode_enabled(config_text: str, plugin_id: str, enabled: bool) -> str:
    """Return new ``opencode.json`` text toggling a plugin's presence.

    OpenCode models enabled state as membership in the ``plugin`` array.
    ``enabled=True`` adds the id (idempotent); ``enabled=False`` removes it and
    raises ``PluginNotFound`` if it is absent.

    Raises ``AgentConfigParseError`` on malformed JSON.
    """
    data = _safe_parse_json(config_text)
    items = _opencode_plugin_list(data)
    if enabled:
        if plugin_id not in items:
            items.append(plugin_id)
    else:
        if plugin_id not in items:
            raise PluginNotFound(plugin_id)
        items = [i for i in items if i != plugin_id]
    data["plugin"] = items
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def remove_opencode_entry(config_text: str, plugin_id: str) -> str:
    """Return new ``opencode.json`` text with the plugin removed from ``plugin``.

    Raises ``PluginNotFound`` if absent, ``AgentConfigParseError`` on bad JSON.
    """
    data = _safe_parse_json(config_text)
    items = _opencode_plugin_list(data)
    if plugin_id not in items:
        raise PluginNotFound(plugin_id)
    data["plugin"] = [i for i in items if i != plugin_id]
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# OpenClaw (the plugins{} block in openclaw.json)
# ---------------------------------------------------------------------------
#
# OpenClaw's plugins schema is only partly documented. We read tolerantly: the
# id universe is the ``entries`` list (strings or ``{id|name}`` dicts); enabled
# state is derived from ``enabled``/``allow`` (allow-lists) and ``deny``
# (deny-list). When no allow-list is present, a plugin is enabled unless denied.


def _openclaw_block(data: dict[str, Any]) -> dict[str, Any]:
    block = data.get("plugins")
    return block if isinstance(block, dict) else {}


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if isinstance(v, str)]


def _openclaw_entry_id(raw: Any) -> str | None:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        ident = raw.get("id") or raw.get("name")
        return str(ident) if isinstance(ident, str) and ident else None
    return None


def _openclaw_entry_ids(block: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for raw in block.get("entries", []) if isinstance(block.get("entries"), list) else []:
        ident = _openclaw_entry_id(raw)
        if ident is not None and ident not in ids:
            ids.append(ident)
    return ids


def parse_openclaw(config_json: str | None) -> tuple[list[PluginInfo], list[MarketplaceInfo]]:
    """Parse OpenClaw plugin state from the ``plugins`` block of ``openclaw.json``.

    Tolerant of the partly documented shape: ``entries`` enumerates ids,
    ``enabled``/``allow`` are allow-lists, ``deny`` is a deny-list. A plugin is
    enabled when listed in an allow-list (if any exists) and not denied; with no
    allow-list it is enabled unless denied. No marketplace concept.

    Raises ``AgentConfigParseError`` on malformed JSON.
    """
    data = _safe_parse_json(config_json)
    block = _openclaw_block(data)
    allow = set(_str_list(block.get("enabled")) + _str_list(block.get("allow")))
    deny = set(_str_list(block.get("deny")))
    has_allow = bool(allow)

    plugins: list[PluginInfo] = []
    for ident in _openclaw_entry_ids(block):
        if ident in deny:
            enabled = False
        elif has_allow:
            enabled = ident in allow
        else:
            enabled = True
        plugins.append(PluginInfo(id=ident, name=ident, marketplace="", enabled=enabled))
    return plugins, []


def _openclaw_require(block: dict[str, Any], plugin_id: str) -> None:
    if plugin_id not in _openclaw_entry_ids(block):
        raise PluginNotFound(plugin_id)


def set_openclaw_enabled(config_text: str, plugin_id: str, enabled: bool) -> str:
    """Return new ``openclaw.json`` text toggling a plugin in the ``plugins`` block.

    Maintains the ``enabled`` allow-list and the ``deny`` deny-list: enabling
    adds to ``enabled`` and drops from ``deny``; disabling adds to ``deny`` and
    drops from ``enabled``.

    Raises ``PluginNotFound`` if the id is not an entry; ``AgentConfigParseError``
    on malformed JSON.
    """
    data = _safe_parse_json(config_text)
    block = _openclaw_block(data)
    _openclaw_require(block, plugin_id)

    enabled_list = _str_list(block.get("enabled"))
    deny_list = _str_list(block.get("deny"))
    if enabled:
        if plugin_id not in enabled_list:
            enabled_list.append(plugin_id)
        deny_list = [i for i in deny_list if i != plugin_id]
    else:
        if plugin_id not in deny_list:
            deny_list.append(plugin_id)
        enabled_list = [i for i in enabled_list if i != plugin_id]

    block["enabled"] = enabled_list
    block["deny"] = deny_list
    data["plugins"] = block
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def remove_openclaw_entry(config_text: str, plugin_id: str) -> str:
    """Return new ``openclaw.json`` text with the plugin removed from the block.

    Drops the id from ``entries``, ``enabled``/``allow``, and ``deny``.

    Raises ``PluginNotFound`` if absent, ``AgentConfigParseError`` on bad JSON.
    """
    data = _safe_parse_json(config_text)
    block = _openclaw_block(data)
    _openclaw_require(block, plugin_id)

    entries = block.get("entries")
    if isinstance(entries, list):
        block["entries"] = [e for e in entries if _openclaw_entry_id(e) != plugin_id]
    for key in ("enabled", "allow", "deny"):
        if isinstance(block.get(key), list):
            block[key] = [i for i in block[key] if i != plugin_id]
    data["plugins"] = block
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

"""Parse and toggle agent plugin state for Codex and Claude Code.

Pure domain text transforms — no filesystem access.

Codex stores plugin configuration in ``~/.codex/config.toml``:
- ``[marketplaces.<name>]`` tables describe plugin sources (source_type, source).
- ``[plugins."<name>@<marketplace>"]`` tables hold per-plugin state; ``enabled``
  defaults to ``true`` when absent.  Coffer may read and write this file directly
  via tomlkit round-trip (documented write surface).

Claude Code splits plugin state across three files:
- ``~/.claude/plugins/installed_plugins.json`` (INTERNAL, read-only): inventory
  of installed plugins; shape ``{"version": 2, "plugins": {"<id>": [...]}}``.
- ``~/.claude/plugins/known_marketplaces.json`` (INTERNAL, read-only): known
  marketplace metadata; shape ``{"<mkt>": {"source": {"source": ..., "repo": ...}}}``.
- ``~/.claude/settings.json`` (DOCUMENTED write surface): ``enabledPlugins`` map
  ``{"<id>": true|false}``.

**Coffer must only ever WRITE settings.json for Claude Code** — never the two
internal files.  ``set_claude_enabled`` encodes this constraint by accepting only
the settings text as a mutable input.
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any

import tomlkit

from coffer.domain.agent.mcp_entries import _parse_json, _parse_toml
from coffer.domain.errors import ConfigFileFormatInvalid
from coffer.domain.workspace_errors import AgentConfigParseError, PluginNotFound

# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PluginInfo:
    """One installed plugin (derived, never stored)."""

    id: str  # "<name>@<marketplace>"
    name: str
    marketplace: str
    enabled: bool
    # Whether the plugin appears in the agent's install inventory (Codex
    # config / Claude installed_plugins.json) — settings-only orphans get
    # False. Drives cache_present without re-parsing in the service.
    installed: bool = True


@dataclass(frozen=True)
class MarketplaceInfo:
    """One configured plugin marketplace (derived, read-only)."""

    name: str
    source_type: str | None = None
    source: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_id(plugin_id: str) -> tuple[str, str]:
    """Split ``"<name>@<marketplace>"`` on the LAST ``@``.

    Returns ``(name, marketplace)``.  If there is no ``@``, marketplace is ``""``.
    """
    if "@" in plugin_id:
        at = plugin_id.rfind("@")
        return plugin_id[:at], plugin_id[at + 1 :]
    return plugin_id, ""


# ---------------------------------------------------------------------------
# Codex
# ---------------------------------------------------------------------------


def parse_codex(text: str) -> tuple[list[PluginInfo], list[MarketplaceInfo]]:
    """Parse plugin state from a Codex ``config.toml`` text.

    Returns ``(plugins, marketplaces)``.  Raises ``AgentConfigParseError`` on
    malformed TOML.
    """
    try:
        doc = _parse_toml(text)
    except ConfigFileFormatInvalid as e:
        raise AgentConfigParseError("<config>", str(e)) from e

    plugins: list[PluginInfo] = []
    raw_plugins = doc.get("plugins")
    if isinstance(raw_plugins, MutableMapping):
        for plugin_id, raw in raw_plugins.items():
            if not isinstance(raw, MutableMapping):
                continue
            enabled = bool(raw.get("enabled", True))
            name, marketplace = _split_id(str(plugin_id))
            plugins.append(
                PluginInfo(id=str(plugin_id), name=name, marketplace=marketplace, enabled=enabled)
            )

    marketplaces: list[MarketplaceInfo] = []
    raw_marketplaces = doc.get("marketplaces")
    if isinstance(raw_marketplaces, MutableMapping):
        for mkt_name, raw in raw_marketplaces.items():
            if not isinstance(raw, MutableMapping):
                marketplaces.append(MarketplaceInfo(name=str(mkt_name)))
                continue
            source_type = str(raw["source_type"]) if raw.get("source_type") is not None else None
            source = str(raw["source"]) if raw.get("source") is not None else None
            marketplaces.append(
                MarketplaceInfo(name=str(mkt_name), source_type=source_type, source=source)
            )

    return plugins, marketplaces


def set_codex_enabled(text: str, plugin_id: str, enabled: bool) -> str:
    """Return new TOML text with the named Codex plugin's ``enabled`` flag set.

    Raises ``PluginNotFound`` if the plugin does not exist or its entry is not a
    table.  Raises ``AgentConfigParseError`` on malformed TOML.
    """
    try:
        doc = _parse_toml(text)
    except ConfigFileFormatInvalid as e:
        raise AgentConfigParseError("<config>", str(e)) from e

    plugins = doc.get("plugins")
    if not isinstance(plugins, MutableMapping) or plugin_id not in plugins:
        raise PluginNotFound(plugin_id)
    entry = plugins[plugin_id]
    if not isinstance(entry, MutableMapping):
        raise PluginNotFound(plugin_id)

    doc["plugins"][plugin_id]["enabled"] = enabled
    return tomlkit.dumps(doc)


def remove_codex_entry(text: str, plugin_id: str) -> str:
    """Return new TOML text with the named Codex plugin entry removed.

    Raises ``PluginNotFound`` if the plugin does not exist.
    Raises ``AgentConfigParseError`` on malformed TOML.
    If the ``plugins`` table becomes empty it is left in place (not pruned).
    """
    try:
        doc = _parse_toml(text)
    except ConfigFileFormatInvalid as e:
        raise AgentConfigParseError("<config>", str(e)) from e

    plugins = doc.get("plugins")
    if not isinstance(plugins, MutableMapping) or plugin_id not in plugins:
        raise PluginNotFound(plugin_id)

    del doc["plugins"][plugin_id]
    return tomlkit.dumps(doc)


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------


def _safe_parse_json(text: str | None) -> dict[str, Any]:
    """Parse JSON text, treating ``None`` or empty string as ``{}``."""
    if not text or not text.strip():
        return {}
    try:
        return _parse_json(text)
    except ConfigFileFormatInvalid as e:
        raise AgentConfigParseError("<config>", str(e)) from e


def parse_claude(
    *,
    installed_json: str | None,
    marketplaces_json: str | None,
    settings_json: str | None,
) -> tuple[list[PluginInfo], list[MarketplaceInfo]]:
    """Parse plugin state from Claude Code's three config files.

    All inputs are optional (``None`` or empty string → treated as ``{}``).
    Plugin IDs are the union of ``installed_plugins.json`` and
    ``settings.json["enabledPlugins"]`` keys: installed first, then
    settings-only extras.  Enabled state comes from ``settings["enabledPlugins"]``
    with a default of ``True`` for any plugin not listed there.

    Raises ``AgentConfigParseError`` on unparseable JSON.
    """
    installed = _safe_parse_json(installed_json)
    marketplaces_raw = _safe_parse_json(marketplaces_json)
    settings = _safe_parse_json(settings_json)

    enabled_map: dict[str, bool] = {}
    raw_enabled = settings.get("enabledPlugins")
    if isinstance(raw_enabled, dict):
        for k, v in raw_enabled.items():
            enabled_map[str(k)] = bool(v)

    # Build ordered union: installed first, then settings-only extras
    installed_plugins_raw = installed.get("plugins")
    installed_ids: list[str] = []
    if isinstance(installed_plugins_raw, dict):
        installed_ids = [str(k) for k in installed_plugins_raw]

    installed_set: set[str] = set(installed_ids)
    seen: set[str] = set(installed_ids)
    all_ids: list[str] = list(installed_ids)
    for pid in enabled_map:
        if pid not in seen:
            all_ids.append(pid)
            seen.add(pid)

    plugins: list[PluginInfo] = []
    for pid in all_ids:
        enabled = enabled_map.get(pid, True)
        name, marketplace = _split_id(pid)
        plugins.append(
            PluginInfo(
                id=pid,
                name=name,
                marketplace=marketplace,
                enabled=enabled,
                installed=pid in installed_set,
            )
        )

    marketplaces: list[MarketplaceInfo] = []
    for mkt_name, raw in marketplaces_raw.items():
        if not isinstance(raw, dict):
            marketplaces.append(MarketplaceInfo(name=str(mkt_name)))
            continue
        source_raw = raw.get("source")
        source_type: str | None = None
        source: str | None = None
        if isinstance(source_raw, dict):
            st = source_raw.get("source")
            source_type = str(st) if st is not None else None
            repo = source_raw.get("repo")
            source = str(repo) if repo is not None else None
        marketplaces.append(
            MarketplaceInfo(name=str(mkt_name), source_type=source_type, source=source)
        )

    return plugins, marketplaces


def set_claude_enabled(settings_text: str, plugin_id: str, enabled: bool) -> str:
    """Return new ``settings.json`` text with the named plugin's enabled flag set.

    This is the **only** write operation for Claude Code plugins — Coffer must
    never write the internal ``installed_plugins.json`` or
    ``known_marketplaces.json`` files.

    ``settings_text`` may be empty or ``None``-equivalent (e.g., the file does
    not exist yet); in that case an empty settings object is assumed.

    Raises ``AgentConfigParseError`` on malformed JSON.
    """
    data = _safe_parse_json(settings_text)
    enabled_map = data.get("enabledPlugins")
    # A hand-edit may have left a non-object here — replace it, mirroring the
    # tolerance of the read path and mcp_install's mcpServers guard.
    if not isinstance(enabled_map, dict):
        enabled_map = {}
        data["enabledPlugins"] = enabled_map
    enabled_map[plugin_id] = enabled
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

"""AgentPluginService — list / toggle / Codex-uninstall an agent's plugins.

Operates on agent plugin state using the pure text transforms in
``domain/agent/plugin_state.py``.

For **Codex** agents, the documented write surface is ``config.toml`` (the
``config`` key in the allowlist).  The plugin cache directory lives at
``<config_dir>/plugins/cache/<marketplace>/<name>`` and is removed on
uninstall when present.

For **Claude Code** agents, the only documented write surface is
``settings.json`` (the ``settings`` key in the allowlist).  The two internal
inventory files (``installed_plugins.json``, ``known_marketplaces.json``) are
read directly by path — Coffer never writes them.  Uninstall is not supported
for Claude Code; callers should use the agent's own tooling.
"""

from __future__ import annotations

import pathlib
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.application.agent.mcp_entry_service import ParseErrorInfo
from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.plugin_state import (
    MarketplaceInfo,
    parse_claude,
    parse_codex,
    remove_codex_entry,
    set_claude_enabled,
    set_codex_enabled,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.workspace_errors import (
    AgentConfigParseError,
    PluginNotFound,
    PluginUninstallUnsupported,
)


class _AgentLookup(Protocol):
    async def get(self, name: str) -> Resource: ...


@dataclass(frozen=True)
class PluginView:
    """One plugin as seen by API consumers."""

    id: str
    name: str
    marketplace: str
    enabled: bool
    cache_present: bool


@dataclass(frozen=True)
class PluginsOut:
    """Plugin listing response."""

    items: list[PluginView]
    marketplaces: list[MarketplaceInfo]
    parse_errors: list[ParseErrorInfo]


class AgentPluginService:
    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        audit: AuditService,
        store: ConfigFileStorePort,
        dir_exists: Callable[[pathlib.Path], bool] | None = None,
        rmtree: Callable[[pathlib.Path], None] | None = None,
    ) -> None:
        self._agents = agent_service
        self._audit = audit
        self._store = store
        self._dir_exists: Callable[[pathlib.Path], bool] = (
            dir_exists if dir_exists is not None else lambda p: p.is_dir()
        )
        self._rmtree: Callable[[pathlib.Path], None] = (
            rmtree if rmtree is not None else shutil.rmtree
        )

    async def _config_for(self, name: str) -> AgentConfig:
        resource = await self._agents.get(name)
        return AgentConfig.model_validate(resource.config)

    # ------------------------------------------------------------------
    # list_plugins
    # ------------------------------------------------------------------

    async def list_plugins(self, name: str) -> PluginsOut:
        """Return all plugins for the named agent with metadata."""
        cfg = await self._config_for(name)
        cfg_dir = cfg.resolved_config_dir()

        if cfg.type is AgentType.CODEX:
            return await self._list_codex(cfg_dir)
        # AgentType.CLAUDE_CODE
        return await self._list_claude(cfg_dir)

    async def _list_codex(self, cfg_dir: pathlib.Path) -> PluginsOut:
        spec = spec_for(AgentType.CODEX, "config", cfg_dir)
        text = self._store.read_text(spec.path)
        if text is None:
            return PluginsOut(items=[], marketplaces=[], parse_errors=[])

        try:
            plugins, marketplaces = parse_codex(text)
        except AgentConfigParseError as e:
            return PluginsOut(
                items=[],
                marketplaces=[],
                parse_errors=[ParseErrorInfo(source="config", path=str(spec.path), error=str(e))],
            )

        cache_root = cfg_dir / "plugins" / "cache"
        items = [
            PluginView(
                id=p.id,
                name=p.name,
                marketplace=p.marketplace,
                enabled=p.enabled,
                cache_present=self._dir_exists(cache_root / p.marketplace / p.name),
            )
            for p in plugins
        ]
        return PluginsOut(items=items, marketplaces=list(marketplaces), parse_errors=[])

    async def _list_claude(self, cfg_dir: pathlib.Path) -> PluginsOut:
        plugins_dir = cfg_dir / "plugins"
        installed_json = self._store.read_text(plugins_dir / "installed_plugins.json")
        marketplaces_json = self._store.read_text(plugins_dir / "known_marketplaces.json")

        spec = spec_for(AgentType.CLAUDE_CODE, "settings", cfg_dir)
        settings_json = self._store.read_text(spec.path)

        try:
            plugins, marketplaces = parse_claude(
                installed_json=installed_json,
                marketplaces_json=marketplaces_json,
                settings_json=settings_json,
            )
        except AgentConfigParseError as e:
            return PluginsOut(
                items=[],
                marketplaces=[],
                parse_errors=[
                    ParseErrorInfo(source="plugins", path=str(plugins_dir), error=str(e))
                ],
            )

        # cache_present for Claude = "appears in the install inventory" (we do
        # not model its cache dirs); the domain parser owns that distinction.
        items = [
            PluginView(
                id=p.id,
                name=p.name,
                marketplace=p.marketplace,
                enabled=p.enabled,
                cache_present=p.installed,
            )
            for p in plugins
        ]
        return PluginsOut(items=items, marketplaces=list(marketplaces), parse_errors=[])

    # ------------------------------------------------------------------
    # set_enabled
    # ------------------------------------------------------------------

    async def set_enabled(
        self, name: str, plugin_id: str, enabled: bool, *, actor: str = "api"
    ) -> None:
        """Enable or disable a plugin by id."""
        cfg = await self._config_for(name)
        cfg_dir = cfg.resolved_config_dir()

        if cfg.type is AgentType.CODEX:
            spec = spec_for(AgentType.CODEX, "config", cfg_dir)
            text = self._store.read_text(spec.path)
            if text is None:
                raise PluginNotFound(plugin_id)
            new_text = set_codex_enabled(text, plugin_id, enabled)
            self._store.write_text_atomic(spec.path, new_text)
        else:
            # claude_code — write settings.json only; create if missing
            spec = spec_for(AgentType.CLAUDE_CODE, "settings", cfg_dir)
            text = self._store.read_text(spec.path) or ""
            new_text = set_claude_enabled(text, plugin_id, enabled)
            self._store.write_text_atomic(spec.path, new_text)

        await self._audit.record(
            AuditEventType.AGENT_PLUGIN_TOGGLED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"plugin": plugin_id, "enabled": enabled},
        )

    # ------------------------------------------------------------------
    # uninstall
    # ------------------------------------------------------------------

    async def uninstall(self, name: str, plugin_id: str, *, actor: str = "api") -> None:
        """Remove a plugin entry and its cache (Codex only)."""
        cfg = await self._config_for(name)
        cfg_dir = cfg.resolved_config_dir()

        if cfg.type is not AgentType.CODEX:
            raise PluginUninstallUnsupported(cfg.type.value)

        spec = spec_for(AgentType.CODEX, "config", cfg_dir)
        text = self._store.read_text(spec.path)
        if text is None:
            raise PluginNotFound(plugin_id)
        # remove_codex_entry raises PluginNotFound if not present
        new_text = remove_codex_entry(text, plugin_id)
        self._store.write_text_atomic(spec.path, new_text)

        # Remove the cache directory if present.
        # plugin_id = "<name>@<marketplace>"; split on last '@'
        if "@" in plugin_id:
            at = plugin_id.rfind("@")
            plugin_name = plugin_id[:at]
            marketplace = plugin_id[at + 1 :]
        else:
            plugin_name = plugin_id
            marketplace = ""

        cache_dir = cfg_dir / "plugins" / "cache" / marketplace / plugin_name
        cache_removed = self._dir_exists(cache_dir)
        # Audit before the cache cleanup: the config entry (source of truth)
        # is already removed, so the event must survive an rmtree failure.
        await self._audit.record(
            AuditEventType.AGENT_PLUGIN_UNINSTALLED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"plugin": plugin_id, "cache_removed": cache_removed},
        )
        if cache_removed:
            self._rmtree(cache_dir)

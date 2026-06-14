"""AgentPluginService — list / toggle / uninstall an agent's plugins.

Operates on agent plugin state using the pure text transforms in
``domain/agent/plugin_state.py`` (Claude Code, Codex) and
``domain/agent/plugin_state_extra.py`` (Cursor, OpenCode, OpenClaw).

The per-agent behaviour is data, not control flow: each agent's
:class:`~coffer.domain.agent.descriptor.PluginCapability` (read from the
capability manifest) carries the :class:`PluginModel` strategy discriminator,
the allowlist ``config_key`` of the write surface, and the ``can_toggle`` /
``can_uninstall`` flags. The service dispatches on those — it never switches on
:class:`AgentType`.

Agents with no plugin capability (Hermes — MCP *is* the plugin mechanism)
return an empty listing; toggle and uninstall raise the matching "unsupported"
error.

Write-surface notes preserved from the original behaviour:
- **Codex** writes ``config.toml`` (``config`` key) and removes the plugin
  cache at ``<config_dir>/plugins/cache/<marketplace>/<name>`` on uninstall.
- **Claude Code** writes only ``settings.json`` (``settings`` key); the two
  internal inventory files are read by path and never written. Uninstall is not
  supported.
- **Cursor** is read-only: extensions are listed from
  ``<config_dir>/extensions/extensions.json``; toggle/uninstall are unsupported.
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
from coffer.domain.agent.descriptor import PluginCapability, PluginModel, descriptor_for
from coffer.domain.agent.plugin_state import (
    MarketplaceInfo,
    PluginInfo,
    parse_claude,
    parse_codex,
    remove_codex_entry,
    set_claude_enabled,
    set_codex_enabled,
)
from coffer.domain.agent.plugin_state_extra import (
    parse_cursor,
    parse_openclaw,
    parse_opencode,
    remove_openclaw_entry,
    remove_opencode_entry,
    set_openclaw_enabled,
    set_opencode_enabled,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.workspace_errors import (
    AgentConfigParseError,
    PluginNotFound,
    PluginToggleUnsupported,
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


def _empty() -> PluginsOut:
    return PluginsOut(items=[], marketplaces=[], parse_errors=[])


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

    async def _capability(self, name: str) -> tuple[AgentConfig, PluginCapability | None]:
        cfg = await self._config_for(name)
        return cfg, descriptor_for(cfg.type).plugins

    # ------------------------------------------------------------------
    # list_plugins
    # ------------------------------------------------------------------

    async def list_plugins(self, name: str) -> PluginsOut:
        """Return all plugins for the named agent with metadata."""
        cfg, cap = await self._capability(name)
        if cap is None:
            return _empty()
        cfg_dir = cfg.resolved_config_dir()

        if cap.model is PluginModel.CODEX:
            return self._list_codex(cfg, cfg_dir)
        if cap.model is PluginModel.CLAUDE:
            return self._list_claude(cfg, cfg_dir)
        if cap.model is PluginModel.CURSOR_RO:
            return self._list_text(cfg_dir / "extensions" / "extensions.json", parse_cursor)
        if cap.model is PluginModel.OPENCODE:
            return self._list_text(self._surface_path(cfg, cap), parse_opencode)
        # PluginModel.OPENCLAW
        return self._list_text(self._surface_path(cfg, cap), parse_openclaw)

    def _surface_path(self, cfg: AgentConfig, cap: PluginCapability) -> pathlib.Path:
        """Resolve the write-surface file path from the capability's config_key."""
        assert cap.config_key is not None  # callers guard list-only models
        return spec_for(cfg.type, cap.config_key, cfg.resolved_config_dir()).path

    def _list_text(
        self,
        path: pathlib.Path,
        parse: Callable[[str | None], tuple[list[PluginInfo], list[MarketplaceInfo]]],
    ) -> PluginsOut:
        """List plugins from a single JSON file via a pure-text parser.

        Used by Cursor / OpenCode / OpenClaw — none of which model a plugin
        cache, so ``cache_present`` mirrors the install state (always True for a
        listed entry). A parse failure degrades to an explicit ``parse_errors``
        listing rather than raising.
        """
        text = self._store.read_text(path)
        if text is None:
            return _empty()
        try:
            plugins, marketplaces = parse(text)
        except AgentConfigParseError as e:
            return PluginsOut(
                items=[],
                marketplaces=[],
                parse_errors=[ParseErrorInfo(source="config", path=str(path), error=str(e))],
            )
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

    def _list_codex(self, cfg: AgentConfig, cfg_dir: pathlib.Path) -> PluginsOut:
        spec = spec_for(cfg.type, "config", cfg_dir)
        text = self._store.read_text(spec.path)
        if text is None:
            return _empty()

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

    def _list_claude(self, cfg: AgentConfig, cfg_dir: pathlib.Path) -> PluginsOut:
        plugins_dir = cfg_dir / "plugins"
        installed_json = self._store.read_text(plugins_dir / "installed_plugins.json")
        marketplaces_json = self._store.read_text(plugins_dir / "known_marketplaces.json")

        spec = spec_for(cfg.type, "settings", cfg_dir)
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
        cfg, cap = await self._capability(name)
        if cap is None or not cap.can_toggle:
            raise PluginToggleUnsupported(cfg.type.value)
        spec_path = self._surface_path(cfg, cap)

        if cap.model is PluginModel.CODEX:
            text = self._store.read_text(spec_path)
            if text is None:
                raise PluginNotFound(plugin_id)
            new_text = set_codex_enabled(text, plugin_id, enabled)
        elif cap.model is PluginModel.CLAUDE:
            # write settings.json only; create if missing
            text = self._store.read_text(spec_path) or ""
            new_text = set_claude_enabled(text, plugin_id, enabled)
        elif cap.model is PluginModel.OPENCODE:
            text = self._store.read_text(spec_path)
            if text is None:
                raise PluginNotFound(plugin_id)
            new_text = set_opencode_enabled(text, plugin_id, enabled)
        else:  # PluginModel.OPENCLAW
            text = self._store.read_text(spec_path)
            if text is None:
                raise PluginNotFound(plugin_id)
            new_text = set_openclaw_enabled(text, plugin_id, enabled)

        self._store.write_text_atomic(spec_path, new_text)

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
        """Remove a plugin entry (and, for Codex, its cache)."""
        cfg, cap = await self._capability(name)
        if cap is None or not cap.can_uninstall:
            raise PluginUninstallUnsupported(cfg.type.value)
        cfg_dir = cfg.resolved_config_dir()
        spec_path = self._surface_path(cfg, cap)

        if cap.model is PluginModel.CODEX:
            await self._uninstall_codex(name, plugin_id, spec_path, cfg_dir, actor=actor)
            return

        # OpenCode / OpenClaw — remove from the config array/block; no cache.
        text = self._store.read_text(spec_path)
        if text is None:
            raise PluginNotFound(plugin_id)
        if cap.model is PluginModel.OPENCODE:
            new_text = remove_opencode_entry(text, plugin_id)
        else:  # PluginModel.OPENCLAW
            new_text = remove_openclaw_entry(text, plugin_id)
        self._store.write_text_atomic(spec_path, new_text)
        await self._audit.record(
            AuditEventType.AGENT_PLUGIN_UNINSTALLED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"plugin": plugin_id, "cache_removed": False},
        )

    async def _uninstall_codex(
        self,
        name: str,
        plugin_id: str,
        spec_path: pathlib.Path,
        cfg_dir: pathlib.Path,
        *,
        actor: str,
    ) -> None:
        text = self._store.read_text(spec_path)
        if text is None:
            raise PluginNotFound(plugin_id)
        # remove_codex_entry raises PluginNotFound if not present
        new_text = remove_codex_entry(text, plugin_id)
        self._store.write_text_atomic(spec_path, new_text)

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

"""AgentPluginService — list an agent's plugins.

Operates on agent plugin state using the pure text transforms in
``domain/agent/plugin_state.py`` (Claude Code, Codex).

This is a READ surface. Coffer once toggled and uninstalled plugins too;
those paths were removed because they hand-wrote another tool's private config
format, where an upstream change would corrupt it silently. Reading the same
files degrades, at worst, to FR-030's explicit parse-error state.

The per-agent behaviour is data, not control flow: each agent's
:class:`~coffer.domain.agent.descriptor.PluginCapability` (read from the
capability manifest) carries the :class:`PluginModel` strategy discriminator
and the allowlist ``config_key`` the state is read from. The service dispatches
on those — it never switches on :class:`AgentType`.

Where each agent's state is read from:
- **Codex** — ``config.toml`` (``config`` key), plus the presence of the plugin
  cache at ``<config_dir>/plugins/cache/<marketplace>/<name>``.
- **Claude Code** — the enabled map in ``settings.json`` (``settings`` key),
  plus two internal inventory files read by path. None of them is ever written.
"""

from __future__ import annotations

import pathlib
import shutil
from collections.abc import Callable
from typing import Protocol

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.application.agent.mcp_entry_service import ParseErrorInfo
from coffer.application.agent.plugin_views import (
    PluginDetailReader,
    PluginsOut,
    PluginView,
)
from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.plugin_capability import (
    PluginCapability,
    PluginModel,
)
from coffer.domain.agent.plugin_state import (
    PluginInfo,
    parse_claude,
    parse_codex,
)
from coffer.domain.resource import Resource
from coffer.domain.workspace_errors import (
    AgentConfigParseError,
)


class _AgentLookup(Protocol):
    async def get(self, name: str) -> Resource: ...


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
        detail_reader: PluginDetailReader | None = None,
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
        # Optional: when absent the listing carries no per-plugin detail
        # (description / bundled components), only the config-derived fields.
        self._detail_reader = detail_reader

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
            out = self._list_codex(cfg, cfg_dir)
        else:  # PluginModel.CLAUDE
            out = self._list_claude(cfg, cfg_dir)

        return out

    def _surface_path(self, cfg: AgentConfig, cap: PluginCapability) -> pathlib.Path:
        """Resolve the write-surface file path from the capability's config_key."""
        assert cap.config_key is not None  # callers guard list-only models
        return spec_for(cfg.type, cap.config_key, cfg.resolved_config_dir()).path

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

        # Codex's config.toml records neither version nor install path, so the
        # detail reader is handed the cache ``<marketplace>/<name>`` dir and
        # descends into the version subdir itself (mirrors the cache_present
        # check below).
        cache_root = cfg_dir / "plugins" / "cache"
        items = [
            self._view_with_detail(
                p,
                str(cache_root / p.marketplace / p.name),
                self._dir_exists(cache_root / p.marketplace / p.name),
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
        # Per-plugin detail (description + bundled skills/commands/MCP) is read
        # from the install path the inventory recorded, when a reader is wired.
        items = [self._view_with_detail(p, p.install_path, p.installed) for p in plugins]
        return PluginsOut(items=items, marketplaces=list(marketplaces), parse_errors=[])

    def _view_with_detail(
        self, p: PluginInfo, install_path: str | None, cache_present: bool
    ) -> PluginView:
        """Build a PluginView, enriching it with on-disk detail when a reader is
        wired and an install path is known. Shared by Claude and Codex — the only
        difference is how each derives ``install_path`` (Claude records it in its
        inventory; Codex passes the cache ``<marketplace>/<name>`` dir)."""
        detail = (
            self._detail_reader.read(install_path)
            if self._detail_reader is not None and install_path
            else None
        )
        return PluginView(
            id=p.id,
            name=p.name,
            marketplace=p.marketplace,
            enabled=p.enabled,
            cache_present=cache_present,
            version=p.version or (detail.version if detail else None),
            description=detail.description if detail else None,
            author=detail.author if detail else None,
            homepage=detail.homepage if detail else None,
            skills=detail.skills if detail else (),
            commands=detail.commands if detail else (),
            mcp_servers=detail.mcp_servers if detail else (),
        )

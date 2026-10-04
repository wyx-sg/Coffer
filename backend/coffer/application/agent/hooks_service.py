"""AgentHooksService — every hook in an agent's native config, read only
(spec agent-registry "List every hook in the agent's native config").

Lists what the agent will run and where each hook came from: the agent's own
hook-carrying files (the descriptor's ``hook_source_keys``, resolved through
the config-file allowlist) and each enabled plugin's ``hooks/hooks.json``. It
marks the one that is Coffer's own and reports that hook's health by asking
the agent's delivery hook — the delivery-hook entry of its projection facet —
the same marker-and-command comparison the boot repair uses: ``current`` when
the installed command is exactly the one Coffer would write now, ``stale`` when
Coffer's marker carries another command, ``missing`` when there is none. Its
**trust** says whether the agent will run it at all: Codex skips, silently, a
hook the user has not approved in ``/hooks``, so an installed, current hook can
still deliver nothing. The adapter reads the agent's own trust record
(``config.toml``'s ``[hooks.state]`` for Codex); nothing here writes it. The
last time it fired is read from the audit log, where every real fire is
recorded.

Writes nothing, records no audit event. An unparseable file is reported as a
parse error beside the rows the other files yield.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.application.agent.mcp_entry_service import ParseErrorInfo
from coffer.application.agent.plugin_views import PluginDetailView, PluginsOut
from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.agent.hooks import HookHealth, HookRow, HookSource, MalformedHooks, parse_hooks
from coffer.domain.audit import AuditEventType
from coffer.domain.hook_trust import HookTrust
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.domain.memory.delivery import DeliveryAdapter

#: A plugin's hook file, relative to its package root.
PLUGIN_HOOKS_FILE = pathlib.Path("hooks") / "hooks.json"


class _AgentLookup(Protocol):
    async def get(self, uid: str, /) -> Resource: ...


class _Plugins(Protocol):
    async def list_plugins(self, uid: str) -> PluginsOut: ...
    async def get_plugin(self, uid: str, plugin_id: str) -> PluginDetailView: ...


@dataclass(frozen=True)
class NativeHook:
    event: str
    matcher: str | None
    command: str
    type: str
    timeout: int | None
    #: Position in the file: ``hooks.<event>[group_index].hooks[hook_index]``.
    group_index: int
    hook_index: int
    source: HookSource
    #: The file the hook is declared in.
    path: str
    #: The plugin that contributes it, for a ``plugin`` hook.
    plugin: str | None
    #: Whether this is Coffer's own delivery hook.
    coffer: bool


@dataclass(frozen=True)
class CofferHook:
    """Coffer's own delivery hook for this agent — its entries on every event."""

    #: The events Coffer's entries sit on, comma-joined.
    event: str
    path: str
    health: HookHealth
    #: Whether the agent will run it: ``trusted``, ``untrusted``,
    #: ``modified`` (approved for an earlier command), ``disabled``,
    #: ``unknown``, or ``not_required`` for an agent with no review step.
    trust: HookTrust
    #: What is installed, when something carrying Coffer's marker is.
    installed_command: str | None
    #: What Coffer would write now.
    expected_command: str
    last_fired_at: datetime | None


@dataclass(frozen=True)
class AgentHooks:
    items: tuple[NativeHook, ...]
    #: ``None`` when the agent's projection has no delivery hook.
    coffer_hook: CofferHook | None
    parse_errors: tuple[ParseErrorInfo, ...]


class AgentHooksService:
    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        store: ConfigFileStorePort,
        plugins: _Plugins,
        audit: AuditService,
        catalog: AgentCatalog,
    ) -> None:
        self._agents = agent_service
        self._store = store
        self._plugins = plugins
        self._audit = audit
        self._catalog = catalog

    async def list_hooks(self, uid: str) -> AgentHooks:
        agent = await self._agents.get(uid)
        cfg = AgentConfig.model_validate(agent.config)
        descriptor = self._catalog.get(cfg.type)
        hook = self._catalog.delivery_hook(cfg.type)
        config_dir = cfg.resolved_config_dir()

        files: list[tuple[HookSource, str, pathlib.Path, str | None]] = [
            (HookSource.USER, key, spec_for(cfg.type, key, config_dir).path, None)
            for key in descriptor.hook_source_keys
        ]
        files.extend(await self._plugin_files(uid))

        items: list[NativeHook] = []
        errors: list[ParseErrorInfo] = []
        for source, label, path, plugin in files:
            text = self._store.read_text(path)
            if text is None:
                continue
            try:
                rows = parse_hooks(text)
            except MalformedHooks as e:
                errors.append(ParseErrorInfo(source=label, path=str(path), error=str(e)))
                continue
            items.extend(self._native(row, source, path, plugin, hook) for row in rows)

        coffer = await self._coffer_hook(agent, cfg, hook) if hook is not None else None
        return AgentHooks(items=tuple(items), coffer_hook=coffer, parse_errors=tuple(errors))

    async def coffer_hook(self, uid: str) -> CofferHook | None:
        """Only Coffer's own delivery hook (health, trust, last fire), without
        reading every hook file or plugin: what the attention list asks."""
        agent = await self._agents.get(uid)
        cfg = AgentConfig.model_validate(agent.config)
        hook = self._catalog.delivery_hook(cfg.type)
        return await self._coffer_hook(agent, cfg, hook) if hook is not None else None

    # --- internals -----------------------------------------------------------

    @staticmethod
    def _native(
        row: HookRow,
        source: HookSource,
        path: pathlib.Path,
        plugin: str | None,
        hook: DeliveryAdapter | None,
    ) -> NativeHook:
        is_coffer = hook is not None and hook.is_coffer_command(row.command)
        return NativeHook(
            event=row.event,
            matcher=row.matcher,
            command=row.command,
            type=row.type,
            timeout=row.timeout,
            group_index=row.group_index,
            hook_index=row.hook_index,
            source=source,
            path=str(path),
            plugin=plugin,
            coffer=bool(is_coffer),
        )

    async def _plugin_files(
        self, uid: str
    ) -> list[tuple[HookSource, str, pathlib.Path, str | None]]:
        """Each enabled plugin's hook file, where its package is on disk. A
        disabled plugin's hooks do not run, so they are not listed."""
        out: list[tuple[HookSource, str, pathlib.Path, str | None]] = []
        listing = await self._plugins.list_plugins(uid)
        for view in listing.items:
            if not view.enabled or not view.cache_present:
                continue
            detail = await self._plugins.get_plugin(uid, view.id)
            if detail.install_path is None:
                continue
            path = pathlib.Path(detail.install_path) / PLUGIN_HOOKS_FILE
            out.append((HookSource.PLUGIN, f"plugin:{view.id}", path, view.id))
        return out

    async def _coffer_hook(
        self, agent: Resource, cfg: AgentConfig, hook: DeliveryAdapter
    ) -> CofferHook:
        """``hook`` is the delivery-hook entry of the agent's projection facet."""
        config_dir = cfg.resolved_config_dir()
        path = spec_for(cfg.type, hook.config_key, config_dir).path
        text = self._store.read_text(path) or ""
        expected = hook.command_for(agent.uid)
        try:
            found = hook.find_all(text)
        except Exception:
            # An unparseable file is already a parse error in the listing.
            found = []
        commands = sorted({h.command for h in found})
        installed = " | ".join(commands) if commands else None
        events = ",".join(sorted({h.event for h in found}))
        trust_text: str | None = None
        if hook.trust_config_key is not None:
            trust_path = spec_for(cfg.type, hook.trust_config_key, config_dir).path
            trust_text = self._store.read_text(trust_path)
        trust = hook.trust(text, trust_text, str(path))
        if installed is None:
            health = HookHealth.MISSING
        elif installed == expected and events == hook.event:
            health = HookHealth.CURRENT
        else:
            health = HookHealth.STALE
        fired = await self._audit.query(
            resource=agent, event_type=AuditEventType.MEMORY_DELIVERY_FIRED.value, limit=1
        )
        return CofferHook(
            # Where it sits when installed, where it would go otherwise.
            event=events or hook.event,
            path=str(path),
            health=health,
            trust=trust,
            installed_command=installed,
            expected_command=expected,
            last_fired_at=fired[0].timestamp if fired else None,
        )


__all__ = ["AgentHooks", "AgentHooksService", "CofferHook", "NativeHook"]

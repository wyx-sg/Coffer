"""AgentHooksService — every hook in an agent's native config, read only
(spec agent-registry "List every hook in the agent's native config").

Lists what the agent will run and where each hook came from: the agent's own
hook-carrying files (the descriptor's ``hook_source_keys``, resolved through
the config-file allowlist) and each enabled plugin's ``hooks/hooks.json``.
Coffer installs no hook of its own.

Writes nothing, records no audit event. An unparseable file is reported as a
parse error beside the rows the other files yield.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Protocol

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.application.agent.mcp_entry_service import ParseErrorInfo
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.agent.hooks import HookRow, HookSource, MalformedHooks, parse_hooks
from coffer.domain.resource import Resource

#: A plugin's hook file, relative to its package root.
PLUGIN_HOOKS_FILE = pathlib.Path("hooks") / "hooks.json"


class _AgentLookup(Protocol):
    async def get(self, uid: str, /) -> Resource: ...


class _Plugins(Protocol):
    async def enabled_install_roots(self, uid: str) -> list[tuple[str, str]]: ...


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


@dataclass(frozen=True)
class AgentHooks:
    items: tuple[NativeHook, ...]
    parse_errors: tuple[ParseErrorInfo, ...]


class AgentHooksService:
    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        store: ConfigFileStorePort,
        plugins: _Plugins,
        catalog: AgentCatalog,
    ) -> None:
        self._agents = agent_service
        self._store = store
        self._plugins = plugins
        self._catalog = catalog

    async def list_hooks(self, uid: str) -> AgentHooks:
        agent = await self._agents.get(uid)
        cfg = AgentConfig.model_validate(agent.config)
        descriptor = self._catalog.get(cfg.type)
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
            items.extend(self._native(row, source, path, plugin) for row in rows)

        return AgentHooks(items=tuple(items), parse_errors=tuple(errors))

    # --- internals -----------------------------------------------------------

    @staticmethod
    def _native(
        row: HookRow,
        source: HookSource,
        path: pathlib.Path,
        plugin: str | None,
    ) -> NativeHook:
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
        )

    async def _plugin_files(
        self, uid: str
    ) -> list[tuple[HookSource, str, pathlib.Path, str | None]]:
        """Each enabled plugin's hook file, where its package is on disk. A
        disabled plugin's hooks do not run, so they are not listed."""
        out: list[tuple[HookSource, str, pathlib.Path, str | None]] = []
        for plugin_id, root in await self._plugins.enabled_install_roots(uid):
            path = pathlib.Path(root) / PLUGIN_HOOKS_FILE
            out.append((HookSource.PLUGIN, f"plugin:{plugin_id}", path, plugin_id))
        return out


__all__ = ["AgentHooks", "AgentHooksService", "NativeHook"]

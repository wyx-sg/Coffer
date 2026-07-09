"""AgentHookService — install / uninstall / status for Coffer's lifecycle hooks.

Clones :class:`AgentMcpService`: it resolves an agent to its
:class:`AgentConfig`, reads the descriptor's :class:`ContextInjectionSpec`, and
drives the pure ``domain/agent/hook_install`` transforms through the atomic
config-file store (``write_text_atomic`` keeps a ``.bak``).

The installed command bakes the agent name into the args
(``<coffer-hook> --agent <name>``) because the external hook JSON payload does
not carry Coffer's agent identity — the entrypoint needs it to address the right
agent's session-context / session-end endpoints. For a non-Claude flavor it also
bakes in ``--dialect`` (which stdout envelope to print) and ``--event`` (Cursor's
stdin payload is not guaranteed to name the event; its hooks.json keys it).

This service handles all three ``InjectionMode`` values. For the block mode
(Hermes — no working upstream hook, ADR-042) install renders the FR-044
session-context payload into a marker block in the agent's instructions file
via the pure ``domain/agent/instructions_block`` transforms; the block is
static between refreshes, so :meth:`AgentHookService.refresh_blocks_for_type`
re-renders it and is called (best-effort) before each Coffer-driven turn. For
the plugin-drop mode (opencode — in-process JS callbacks only) install writes
the flavor's plugin file(s) — one flat file for opencode, a package directory
plus an ``openclaw.json`` enable flag for openclaw (``plugin_drop_ops``); the
plugin spawns ``coffer-hook`` live, so it is dynamic like the
shell hooks and has no refresh machinery. An agent whose descriptor declares no
injection — or a block-mode agent when no payload source is wired — raises
:class:`HookInstallUnsupported` (→ 422) on install/uninstall; ``status``
reports ``installed=False, supported=False`` for it (a not-installable agent is
simply not installed, never an error to inspect). Surfaces read ``supported``
to disable the control up front rather than letting a click 422.
"""

from __future__ import annotations

import logging
import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.application.agent.plugin_drop_ops import (
    install_plugin_files,
    plugin_marker_path,
    uninstall_plugin_files,
)
from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import ConfigFileSpec, spec_for
from coffer.domain.agent.context_injection import (
    ContextInjectionSpec,
    HookEvent,
    HookFlavor,
    InjectionMode,
    event_key,
)
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.hook_install import (
    apply_install,
    apply_uninstall,
    is_installed,
)
from coffer.domain.agent.instructions_block import apply_block, has_block, remove_block
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.workspace_errors import HookInstallUnsupported

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class HookInstallStatus:
    installed: bool
    command: str | None
    #: Whether this agent can have Coffer's hook installed at all. False when its
    #: descriptor declares no context injection, or declares a mode this service
    #: does not implement. ``status`` reports it instead of erroring, so a surface
    #: can render a disabled control with a reason rather than one that 422s on
    #: click.
    supported: bool = True


class _AgentLookup(Protocol):
    async def get(self, name: str) -> Resource: ...

    async def list(self) -> list[Resource]: ...


def _hook_command(
    hook_binary: str,
    agent_name: str,
    *,
    flavor: HookFlavor,
    event: HookEvent,
) -> str:
    """The exact command string the agent execs for ``event``.

    Claude/Codex read the event from the hook's stdin payload, so their command is
    just ``<binary> --agent <name>``. Cursor keys hooks.json by event but does not
    guarantee an event field on stdin, so its command carries ``--dialect cursor
    --event sessionStart`` — the dialect also selects the stdout envelope.

    Every part is shell-quoted so a binary path with spaces (e.g. a macOS app
    bundle) or an exotic agent name survive the agent's ``shlex.split`` round-trip
    — the install transform recognises Coffer's own entry by the ``coffer-hook``
    basename of ``argv[0]``.
    """
    cmd = f"{shlex.quote(hook_binary)} --agent {shlex.quote(agent_name)}"
    if flavor is HookFlavor.CLAUDE:
        return cmd
    return (
        f"{cmd} --dialect {shlex.quote(flavor.value)} "
        f"--event {shlex.quote(event_key(flavor, event))}"
    )


def _commands(hook_binary: str, agent_name: str, inj: ContextInjectionSpec) -> dict[HookEvent, str]:
    return {
        event: _hook_command(hook_binary, agent_name, flavor=inj.flavor, event=event)
        for event in inj.events
    }


class AgentHookService:
    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        audit: AuditService,
        store: ConfigFileStorePort,
        # Injected from the composition root (surfaces) so the application layer
        # never imports the infrastructure ``default_hook_resolver`` directly —
        # that would break the application↛infrastructure import contract.
        hook_resolver: Callable[[], str],
        # Assembles the FR-044 session-context payload at global scope; the
        # INSTRUCTIONS_BLOCK mode renders it into the instructions file. Lazy
        # (the memory service is wired after this one). ``None`` → the block
        # mode is unsupported (tests that only exercise shell hooks omit it).
        session_context: Callable[[], Awaitable[str]] | None = None,
    ) -> None:
        self._agents = agent_service
        self._audit = audit
        self._store = store
        self._resolve_hook = hook_resolver
        self._session_context = session_context

    def _injection(self, cfg: AgentConfig) -> ContextInjectionSpec | None:
        """The agent's injection spec, or ``None`` when it has no injection
        point (or ``INSTRUCTIONS_BLOCK`` without a wired payload source)."""
        injection = descriptor_for(cfg.type).context_injection
        if injection is None:
            return None
        if injection.mode is InjectionMode.INSTRUCTIONS_BLOCK and self._session_context is None:
            return None
        return injection

    def _enable_spec(self, cfg: AgentConfig, inj: ContextInjectionSpec) -> ConfigFileSpec | None:
        """The allowlisted config file carrying the plugin flavor's fail-closed
        enable flag (openclaw's ``plugins.entries`` in ``openclaw.json``), or
        ``None`` for a flavor without one (opencode auto-loads by presence)."""
        if inj.plugin_enable_config_key is None:
            return None
        return spec_for(cfg.type, inj.plugin_enable_config_key, cfg.resolved_config_dir())

    def _plugin_command(self, name: str) -> str:
        """Display form of what the dropped plugin execs (argv, not shell).

        Mirrors the argv baked into ``plugin_drop._TEMPLATE``; the unit tests on
        both pin the pair together so they cannot drift silently."""
        hook = self._resolve_hook()
        return f"{hook} --agent {name} --dialect raw --event sessionStart"

    async def _hook_spec(
        self, name: str
    ) -> tuple[ConfigFileSpec, ContextInjectionSpec, AgentConfig]:
        # Raises ResourceNotFound (→ 404) when the agent doesn't exist.
        resource = await self._agents.get(name)
        cfg = AgentConfig.model_validate(resource.config)
        injection = self._injection(cfg)
        if injection is None:
            raise HookInstallUnsupported(cfg.type.value)
        spec = spec_for(cfg.type, injection.config_key, cfg.resolved_config_dir())
        return spec, injection, cfg

    async def status(self, name: str) -> HookInstallStatus:
        # status never errors on an unsupported agent: a type with no hook
        # injection is simply "not installed".
        resource = await self._agents.get(name)
        cfg = AgentConfig.model_validate(resource.config)
        injection = self._injection(cfg)
        if injection is None:
            return HookInstallStatus(installed=False, command=None, supported=False)
        spec = spec_for(cfg.type, injection.config_key, cfg.resolved_config_dir())
        if injection.mode is InjectionMode.PLUGIN_DROP:
            # Presence of Coffer's named plugin file (the package's entry module
            # for the openclaw flavor) == installed.
            marker = plugin_marker_path(spec, injection)
            installed = self._store.read_text(marker) is not None
            command = self._plugin_command(name) if installed else None
            return HookInstallStatus(installed=installed, command=command)
        text = self._store.read_text(spec.path) or ""
        if injection.mode is InjectionMode.INSTRUCTIONS_BLOCK:
            # The block carries the payload itself; there is no command to report.
            return HookInstallStatus(installed=has_block(text), command=None)
        installed = is_installed(
            text, events=injection.events, fmt=spec.format, flavor=injection.flavor
        )
        command = None
        if installed:
            # Report the session-start command — the one that carries the payload.
            command = _commands(self._resolve_hook(), name, injection)[injection.events[0]]
        return HookInstallStatus(installed=installed, command=command)

    async def install(self, name: str, *, actor: str = "api") -> HookInstallStatus:
        spec, inj, cfg = await self._hook_spec(name)
        if inj.mode is InjectionMode.PLUGIN_DROP:
            return await self._install_plugin(name, spec, inj, cfg, actor=actor)
        if inj.mode is InjectionMode.INSTRUCTIONS_BLOCK:
            return await self._install_block(name, spec, actor=actor)
        hook = self._resolve_hook()  # raises ShimNotFound (→ 422) before any write
        commands = _commands(hook, name, inj)
        text = self._store.read_text(spec.path) or ""
        new_text = apply_install(
            text, commands=commands, events=inj.events, fmt=spec.format, flavor=inj.flavor
        )
        self._store.write_text_atomic(spec.path, new_text)
        command = commands[inj.events[0]]
        await self._audit.record(
            AuditEventType.AGENT_HOOK_INSTALLED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"command": command, "path": str(spec.path)},
        )
        return HookInstallStatus(installed=True, command=command)

    async def uninstall(self, name: str, *, actor: str = "api") -> HookInstallStatus:
        spec, inj, cfg = await self._hook_spec(name)
        if inj.mode is InjectionMode.PLUGIN_DROP:
            removed, path = uninstall_plugin_files(
                self._store, spec, inj, enable_spec=self._enable_spec(cfg, inj)
            )
            # No-op success when nothing was installed — don't audit.
            if not removed:
                return HookInstallStatus(installed=False, command=None)
            await self._audit.record(
                AuditEventType.AGENT_HOOK_UNINSTALLED.value,
                ref=ResourceRef("agent", name),
                actor=actor,
                details={"path": str(path)},
            )
            return HookInstallStatus(installed=False, command=None)
        text = self._store.read_text(spec.path)
        if inj.mode is InjectionMode.INSTRUCTIONS_BLOCK:
            # No-op success when not installed — don't write or audit.
            if text is None or not has_block(text):
                return HookInstallStatus(installed=False, command=None)
            self._store.write_text_atomic(spec.path, remove_block(text))
            await self._audit.record(
                AuditEventType.AGENT_HOOK_UNINSTALLED.value,
                ref=ResourceRef("agent", name),
                actor=actor,
                details={"path": str(spec.path)},
            )
            return HookInstallStatus(installed=False, command=None)
        # No-op success when not installed — don't write or audit.
        if text is None or not is_installed(
            text, events=inj.events, fmt=spec.format, flavor=inj.flavor
        ):
            return HookInstallStatus(installed=False, command=None)
        new_text = apply_uninstall(text, events=inj.events, fmt=spec.format, flavor=inj.flavor)
        self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.AGENT_HOOK_UNINSTALLED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"path": str(spec.path)},
        )
        return HookInstallStatus(installed=False, command=None)

    async def _install_plugin(
        self,
        name: str,
        spec: ConfigFileSpec,
        inj: ContextInjectionSpec,
        cfg: AgentConfig,
        *,
        actor: str,
    ) -> HookInstallStatus:
        """Write Coffer's session-context plugin into the agent's plugin
        directory (idempotent: Coffer's namespace — the flat file or the
        openclaw package dir — is overwritten in place; the openclaw flavor
        also flips its fail-closed ``plugins.entries`` enable flag)."""
        hook = self._resolve_hook()  # raises ShimNotFound (→ 422) before any write
        path = install_plugin_files(
            self._store,
            spec,
            inj,
            hook_binary=hook,
            agent_name=name,
            enable_spec=self._enable_spec(cfg, inj),
        )
        command = self._plugin_command(name)
        await self._audit.record(
            AuditEventType.AGENT_HOOK_INSTALLED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"command": command, "path": str(path)},
        )
        return HookInstallStatus(installed=True, command=command)

    async def _install_block(
        self, name: str, spec: ConfigFileSpec, *, actor: str
    ) -> HookInstallStatus:
        """Render the session-context block into the instructions file (install
        and refresh share this write; only install audits)."""
        assert self._session_context is not None  # _injection() gated on it
        payload = await self._session_context()
        text = self._store.read_text(spec.path) or ""
        new_text = apply_block(text, payload=payload)
        if new_text != text:
            self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.AGENT_HOOK_INSTALLED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"path": str(spec.path)},
        )
        return HookInstallStatus(installed=True, command=None)

    async def refresh_blocks_for_type(self, agent_type: AgentType) -> int:
        """Re-render the session-context block for every registered agent of
        ``agent_type`` that has one installed; returns how many were refreshed.

        The block mode is static between writes, so this runs (best-effort)
        before each Coffer-driven turn for the type. Never raises: a failure to
        refresh one agent is logged and must not block the turn. Routine
        refreshes do not audit — only install/uninstall are user actions.
        """
        if self._session_context is None:
            return 0
        refreshed = 0
        try:
            resources = await self._agents.list()
        except Exception:
            log.exception("instructions-block refresh: could not list agents")
            return 0
        # One payload for the whole sweep: the bundle is global-scoped, so every
        # agent of the type gets the identical text (and one daemon-internal
        # assemble instead of N).
        payload: str | None = None
        for resource in resources:
            try:
                cfg = AgentConfig.model_validate(resource.config)
                if cfg.type is not agent_type:
                    continue
                inj = self._injection(cfg)
                if inj is None or inj.mode is not InjectionMode.INSTRUCTIONS_BLOCK:
                    continue
                spec = spec_for(cfg.type, inj.config_key, cfg.resolved_config_dir())
                text = self._store.read_text(spec.path) or ""
                if not has_block(text):
                    continue  # not installed for this agent — nothing to refresh
                if payload is None:
                    payload = await self._session_context()
                new_text = apply_block(text, payload=payload)
                if new_text != text:
                    self._store.write_text_atomic(spec.path, new_text)
                refreshed += 1
            except Exception:
                log.exception("instructions-block refresh failed for agent %r", resource.ref.name)
        return refreshed

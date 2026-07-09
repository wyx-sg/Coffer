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

This service handles ``InjectionMode.SHELL_COMMAND`` only. An agent whose
descriptor declares no injection — or declares one of the not-yet-implemented
modes — raises :class:`HookInstallUnsupported` (→ 422) on install/uninstall;
``status`` reports ``installed=False`` for it (a not-installable agent is simply
not installed, never an error to inspect).
"""

from __future__ import annotations

import shlex
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from coffer.application.agent.config_file_service import ConfigFileStorePort
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
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.workspace_errors import HookInstallUnsupported


@dataclass(frozen=True)
class HookInstallStatus:
    installed: bool
    command: str | None


class _AgentLookup(Protocol):
    async def get(self, name: str) -> Resource: ...


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
    ) -> None:
        self._agents = agent_service
        self._audit = audit
        self._store = store
        self._resolve_hook = hook_resolver

    def _injection(self, cfg: AgentConfig) -> ContextInjectionSpec | None:
        """The agent's shell-command injection spec, or ``None`` when it has no
        injection point or uses a mode this service does not implement."""
        injection = descriptor_for(cfg.type).context_injection
        if injection is None or injection.mode is not InjectionMode.SHELL_COMMAND:
            return None
        return injection

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
            return HookInstallStatus(installed=False, command=None)
        spec = spec_for(cfg.type, injection.config_key, cfg.resolved_config_dir())
        text = self._store.read_text(spec.path) or ""
        installed = is_installed(
            text, events=injection.events, fmt=spec.format, flavor=injection.flavor
        )
        command = None
        if installed:
            # Report the session-start command — the one that carries the payload.
            command = _commands(self._resolve_hook(), name, injection)[injection.events[0]]
        return HookInstallStatus(installed=installed, command=command)

    async def install(self, name: str, *, actor: str = "api") -> HookInstallStatus:
        spec, inj, _cfg = await self._hook_spec(name)
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
        spec, inj, _cfg = await self._hook_spec(name)
        text = self._store.read_text(spec.path)
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

"""AgentHookService — install / uninstall / status for Coffer's lifecycle hooks.

Clones :class:`AgentMcpService`: it resolves an agent to its
:class:`AgentConfig`, reads the descriptor's :class:`ContextInjectionSpec`, and
drives the pure ``domain/agent/hook_install`` transforms through the atomic
config-file store (``write_text_atomic`` keeps a ``.bak``).

One injection mechanism exists (FR-043): a ``coffer-hook`` command entry in the
agent's hooks JSON file. The installed command bakes the agent name into the
args (``<coffer-hook> --agent <name>``) because the external hook JSON payload
does not carry Coffer's agent identity — the entrypoint needs it to address the
right agent's session-context / session-end endpoints.

An agent whose descriptor declares no injection raises
:class:`HookInstallUnsupported` (→ 422) on install/uninstall; ``status`` reports
``installed=False, supported=False`` for it (a not-installable agent is simply
not installed, never an error to inspect). Surfaces read ``supported`` to
disable the control up front rather than letting a click 422.
"""

from __future__ import annotations

import logging
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from coffer.application.agent.config_file_service import ConfigFileStorePort
from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import ConfigFileSpec, spec_for
from coffer.domain.agent.context_injection import ContextInjectionSpec, HookEvent
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.hook_install import (
    apply_install,
    apply_uninstall,
    is_installed,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.workspace_errors import HookInstallUnsupported

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class HookInstallStatus:
    installed: bool
    command: str | None
    #: Whether this agent can have Coffer's hook installed at all. False when its
    #: descriptor declares no context injection. ``status`` reports it instead of
    #: erroring, so a surface can render a disabled control with a reason rather
    #: than one that 422s on click.
    supported: bool = True


class _AgentLookup(Protocol):
    async def get(self, name: str) -> Resource: ...

    async def list(self) -> list[Resource]: ...


def _hook_command(hook_binary: str, agent_name: str) -> str:
    """The exact command string the agent execs.

    Both supported products name the event on the hook's stdin payload, so the
    command is just ``<binary> --agent <name>``.

    Every part is shell-quoted so a binary path with spaces (e.g. a macOS app
    bundle) or an exotic agent name survive the agent's ``shlex.split`` round-trip
    — the install transform recognises Coffer's own entry by the ``coffer-hook``
    basename of ``argv[0]``.
    """
    return f"{shlex.quote(hook_binary)} --agent {shlex.quote(agent_name)}"


def _commands(hook_binary: str, agent_name: str, inj: ContextInjectionSpec) -> dict[HookEvent, str]:
    return {event: _hook_command(hook_binary, agent_name) for event in inj.events}


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
        """The agent's injection spec, or ``None`` when it has no injection point."""
        return descriptor_for(cfg.type).context_injection

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
        text = self._store.read_text(spec.path) or ""
        installed = is_installed(text, events=injection.events, fmt=spec.format)
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
        new_text = apply_install(text, commands=commands, events=inj.events, fmt=spec.format)
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
        if text is None or not is_installed(text, events=inj.events, fmt=spec.format):
            return HookInstallStatus(installed=False, command=None)
        new_text = apply_uninstall(text, events=inj.events, fmt=spec.format)
        self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.AGENT_HOOK_UNINSTALLED.value,
            ref=ResourceRef("agent", name),
            actor=actor,
            details={"path": str(spec.path)},
        )
        return HookInstallStatus(installed=False, command=None)

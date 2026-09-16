"""DeliveryService — install / status / remove Coffer's own session-start-like
hook for an agent the developer drives themselves (spec memory FR-025/FR-026).

**Explicit only.** Nothing installs this as a side effect of registering an
agent, moving its config dir, or aggregating memory — only a direct call to
`install()` ever writes into a settings file, and every install/remove is
audited with its actor. `status()` never writes anything.

Touches an agent's config directory the same way `AgentConfigFileService`
does: through the allowlisted `ConfigFileSpec` from
`domain.agent.config_files.spec_for` (so an unsupported key can never reach
the filesystem), and through an atomic read/write store that leaves a `.bak`
of whatever was there before. The store is typed by this module's own
`AgentConfigWriter` port — the same shape as the agent kind's
`ConfigFileStorePort`, declared here rather than imported, so the memory kind
never imports the agent kind's application layer (the cross-kind contract;
the agent kind's *domain* vocabulary — `AgentConfig`, `spec_for`, `AgentType`
— is the one allowed exception). The composition root injects the same
infrastructure `ConfigFileStore` into both, which satisfies both ports
structurally. This module never opens a config file on its own path.

The actual JSON edit is delegated to `coffer.domain.memory.delivery` (the
marker and the pure text transform) through one `DeliveryAdapter` per agent
type in `coffer.infrastructure.memory.delivery` — which event, which config
key, and, for Codex, the once-per-session guard. `record_fired` is the other
half of FR-026: it is called by whatever actually serves the context (the
`coffer memory context` CLI), never by this service itself, so each audited
fire is a real one.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import ConfigFileSpec, spec_for
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.delivery import (
    DeliveryAdapter,
    DeliveryStatus,
    DeliveryUnsupported,
    MalformedDeliveryConfig,
)
from coffer.domain.resource import Resource, ResourceRef
from coffer.infrastructure.memory.delivery import CLAUDE_CODE_ADAPTER, CODEX_ADAPTER

#: One adapter per agent type Coffer knows how to deliver into (spec memory
#: FR-025 covers exactly the two agents Coffer already reads native memory
#: from). A type with no entry here raises `DeliveryUnsupported`.
_ADAPTERS: dict[AgentType, DeliveryAdapter] = {
    AgentType.CLAUDE_CODE: CLAUDE_CODE_ADAPTER,
    AgentType.CODEX: CODEX_ADAPTER,
}


class AgentConfigWriter(Protocol):
    """The two filesystem operations delivery needs on an agent's config file.

    Deliberately the same shape as the agent kind's `ConfigFileStorePort`
    (minus `stat`, which delivery never calls): the infrastructure
    `ConfigFileStore` satisfies both without knowing about either.
    """

    def read_text(self, path: pathlib.Path) -> str | None:
        """Return file text, or `None` if the file does not exist."""
        ...

    def write_text_atomic(self, path: pathlib.Path, text: str) -> None:
        """Atomically write `text` to `path` (temp file + rename)."""
        ...


# Structural type for the agent-lookup dependency — avoids a hard import of
# AgentService (and keeps this service unit-testable with a fake), mirroring
# AgentConfigFileService's own `_AgentLookup`.
class _AgentLookup(Protocol):
    async def get(self, name: str) -> Resource: ...
    async def list(self) -> list[Resource]: ...


class DeliveryService:
    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        audit: AuditService,
        store: AgentConfigWriter,
    ) -> None:
        self._agents = agent_service
        self._audit = audit
        self._store = store

    async def _config_for(self, name: str) -> AgentConfig:
        # Raises ResourceNotFound (→ 404) when the agent doesn't exist.
        resource = await self._agents.get(name)
        return AgentConfig.model_validate(resource.config)

    @staticmethod
    def _adapter(agent_type: AgentType) -> DeliveryAdapter:
        try:
            return _ADAPTERS[agent_type]
        except KeyError:
            raise DeliveryUnsupported(agent_type.value) from None

    def _spec(self, cfg: AgentConfig, adapter: DeliveryAdapter) -> ConfigFileSpec:
        # ConfigFileNotAllowed would mean the allowlist and this module
        # disagree about the key — a programming error, not a runtime one.
        return spec_for(cfg.type, adapter.config_key, cfg.resolved_config_dir())

    def _read(self, spec: ConfigFileSpec) -> str:
        return self._store.read_text(spec.path) or ""

    @staticmethod
    def _with_path(spec: ConfigFileSpec, fn: Callable[..., str | None], *args: str) -> str | None:
        """Call `fn(*args)`, re-raising `MalformedDeliveryConfig` with the
        file's path attached — a domain function only ever sees text, never
        a path, so this is the one place that can say WHERE parsing failed
        (spec memory FR-025's "fails loudly" requirement)."""
        try:
            return fn(*args)
        except MalformedDeliveryConfig as e:
            raise MalformedDeliveryConfig(f"{spec.path}: {e}") from e

    async def _status_for(self, name: str, cfg: AgentConfig) -> DeliveryStatus:
        adapter = self._adapter(cfg.type)
        spec = self._spec(cfg, adapter)
        text = self._read(spec)
        command = self._with_path(spec, adapter.find_command, text)
        return DeliveryStatus(
            agent=name,
            installed=command is not None,
            command=command or adapter.command_for(name),
            event=adapter.event,
        )

    async def status(self, agent: str | None = None) -> tuple[DeliveryStatus, ...]:
        """Delivery status for `agent`, or for every registered agent that
        has an adapter (types with none are silently skipped, not errored,
        since a mixed-fleet status view shouldn't fail on an untouchable
        one)."""
        if agent is not None:
            cfg = await self._config_for(agent)
            return (await self._status_for(agent, cfg),)
        out: list[DeliveryStatus] = []
        for resource in await self._agents.list():
            try:
                cfg = AgentConfig.model_validate(resource.config)
            except Exception:
                continue
            if cfg.type not in _ADAPTERS:
                continue
            out.append(await self._status_for(resource.name, cfg))
        return tuple(out)

    async def install(self, agent: str, *, actor: str) -> DeliveryStatus:
        """Install Coffer's hook for `agent`. Idempotent: a prior install is
        replaced in place, never duplicated. Always audited with `actor`."""
        cfg = await self._config_for(agent)
        adapter = self._adapter(cfg.type)
        spec = self._spec(cfg, adapter)
        text = self._read(spec)
        new_text = self._with_path(spec, adapter.install, text, agent)
        assert new_text is not None  # install() always returns text, never None
        self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.MEMORY_DELIVERY_INSTALLED.value,
            ref=ResourceRef("agent", agent),
            actor=actor,
            details={"event": adapter.event, "path": str(spec.path)},
        )
        return await self._status_for(agent, cfg)

    async def remove(self, agent: str, *, actor: str) -> DeliveryStatus:
        """Remove Coffer's hook for `agent`. A clean no-op — no write, no
        audit entry — when nothing is installed."""
        cfg = await self._config_for(agent)
        adapter = self._adapter(cfg.type)
        spec = self._spec(cfg, adapter)
        text = self._read(spec)
        if self._with_path(spec, adapter.find_command, text) is None:
            return await self._status_for(agent, cfg)
        new_text = self._with_path(spec, adapter.remove, text)
        assert new_text is not None  # remove() always returns text, never None
        self._store.write_text_atomic(spec.path, new_text)
        await self._audit.record(
            AuditEventType.MEMORY_DELIVERY_REMOVED.value,
            ref=ResourceRef("agent", agent),
            actor=actor,
            details={"event": adapter.event, "path": str(spec.path)},
        )
        return await self._status_for(agent, cfg)

    async def record_fired(self, agent: str) -> None:
        """Record that `agent`'s hook just fired (spec memory FR-026).

        Called by whatever actually serves the context — never by
        `install()`, `status()`, or anything else in this class — so every
        audited fire is a real one. The actor is the agent: nobody clicked
        anything, the hook ran because that agent started a session.
        """
        await self._audit.record(
            AuditEventType.MEMORY_DELIVERY_FIRED.value,
            ref=ResourceRef("agent", agent),
            actor=agent,
        )

"""DeliveryService — install / status / remove Coffer's own session-start-like
hook for an agent the developer drives themselves (spec memory "Install
delivery hooks explicitly and removably", "Audit every delivery fire").

**Explicit only.** Nothing installs this as a side effect of registering an
agent, moving its config dir, or aggregating memory. What calls `install()` is
the user connecting the agent to Coffer (spec agent-registry "Connect an agent
to Coffer in one action", which composes this hook as one of its parts), or the
delivery-hook reconcile target (`delivery_reconcile.py`) repairing a stale
command or following the `memory` switch; every install/remove is audited with
its actor. `status()` never writes anything.

There is one writer. `write_install` / `write_remove` perform the
marker-scoped, atomic, backed-up edit and hand back a `DeliveryWrite` (the
prior text, the new text, the path) without auditing; the public `install` /
`remove` call them and record the audit event, and the reconcile target calls
them and hands the event to the reconciler, which records it and runs
`restore` if it cannot.

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
marker and the pure text transform) through the delivery-hook entry of each
agent's projection facet — a `DeliveryAdapter` from
`coffer.infrastructure.memory.delivery` bound at the composition root (ADR
agent-mechanisms-are-optional-facets-on-the-descriptor): which event, which
config key, and, for Codex, the once-per-session guard. An agent whose
projection has no delivery hook raises `DeliveryUnsupported`. `record_fired` is the other
half of "Audit every delivery fire": it is called by whatever actually serves the context (the
`coffer memory context` CLI), never by this service itself, so each audited
fire is a real one.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import ConfigFileSpec, spec_for
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.delivery import (
    DeliveryAdapter,
    DeliveryStatus,
    DeliveryUnsupported,
    MalformedDeliveryConfig,
)
from coffer.domain.resource import Resource


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

    def delete_with_backup(self, path: pathlib.Path) -> bool:
        """Back `path` up and remove it; `False` when it is absent. Only an
        undo of a write that created the file calls this."""
        ...


# Structural type for the agent-lookup dependency — avoids a hard import of
# AgentService (and keeps this service unit-testable with a fake), mirroring
# AgentConfigFileService's own `_AgentLookup`.
class _AgentLookup(Protocol):
    """How delivery reaches an agent: by uid, never by name.

    ``uid`` is positional-only, so this Protocol is satisfied by whatever the
    agent kind calls its own parameter — the composition root injects
    ``AgentService`` here, and a structural port has no business pinning down a
    keyword nobody passes.
    """

    async def get(self, uid: str, /) -> Resource: ...
    async def list(self) -> list[Resource]: ...


@dataclass(frozen=True)
class HookSite:
    """Where one registered agent's delivery hook lives: the agent, its
    projection's delivery-hook adapter, and the allowlisted file."""

    agent: Resource
    adapter: DeliveryAdapter
    path: pathlib.Path


@dataclass(frozen=True)
class DeliveryWrite:
    """One edit the writer made: what the file held before (`None` when the
    write created it) and what it holds now. What an audit event describes and
    what `DeliveryService.restore` puts back."""

    agent: Resource
    event: str
    path: pathlib.Path
    prior_text: str | None
    new_text: str

    @property
    def details(self) -> dict[str, str]:
        return {"event": self.event, "path": str(self.path)}


class DeliveryService:
    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        audit: AuditService,
        store: AgentConfigWriter,
        catalog: AgentCatalog,
    ) -> None:
        self._agents = agent_service
        self._audit = audit
        self._store = store
        self._catalog = catalog

    async def _agent(self, agent_uid: str) -> tuple[Resource, AgentConfig]:
        """The agent row and its parsed config, together.

        Both halves travel from here because every operation needs both: the
        config decides which adapter and which file, and the row is what the
        audit event is tied to and what the status carries the label from.
        Raises ResourceNotFound (→ 404) when the agent doesn't exist.
        """
        resource = await self._agents.get(agent_uid)
        return resource, AgentConfig.model_validate(resource.config)

    def _adapter(self, agent_type: AgentType) -> DeliveryAdapter:
        adapter = self._catalog.delivery_hook(agent_type)
        if adapter is None:
            raise DeliveryUnsupported(agent_type.value)
        return adapter

    def _spec(self, cfg: AgentConfig, adapter: DeliveryAdapter) -> ConfigFileSpec:
        # ConfigFileNotAllowed would mean the allowlist and this module
        # disagree about the key — a programming error, not a runtime one.
        return spec_for(cfg.type, adapter.config_key, cfg.resolved_config_dir())

    def _read(self, spec: ConfigFileSpec) -> str:
        return self._store.read_text(spec.path) or ""

    @staticmethod
    def _with_path(spec: ConfigFileSpec, fn: Callable[..., str | None], *args: str) -> str | None:
        """Call `fn(*args)`, re-raising `MalformedDeliveryConfig` with the file's path
        attached — a domain function only ever sees text, never a path, so this is the
        one place that can say WHERE parsing failed. "Install delivery hooks explicitly
        and removably" makes an install an explicit, removable act, and neither is
        actionable when a refusal cannot name the file that is malformed."""
        try:
            return fn(*args)
        except MalformedDeliveryConfig as e:
            raise MalformedDeliveryConfig(f"{spec.path}: {e}") from e

    async def _status_for(self, agent: Resource, cfg: AgentConfig) -> DeliveryStatus:
        adapter = self._adapter(cfg.type)
        spec = self._spec(cfg, adapter)
        text = self._read(spec)
        command = self._with_path(spec, adapter.find_command, text)
        return DeliveryStatus(
            agent_uid=agent.uid,
            agent_name=agent.name,
            installed=command is not None,
            # What IS installed when something is, otherwise what an install
            # would write. Both spell the agent by uid; the name beside them is
            # for the person reading the row, and never goes into the command.
            command=command or adapter.command_for(agent.uid),
            event=adapter.event,
        )

    def supports(self, agent_type: AgentType) -> bool:
        """Whether the agent's projection has a delivery hook."""
        return self._catalog.delivery_hook(agent_type) is not None

    async def status(self, agent_uid: str) -> DeliveryStatus:
        """Whether the hook is installed for one agent. Writes nothing."""
        agent, cfg = await self._agent(agent_uid)
        return await self._status_for(agent, cfg)

    async def sites(self) -> list[HookSite]:
        """Every registered agent whose projection has a delivery hook, with
        the file it lives in. Reads no config file; an agent row whose config
        does not parse is left out."""
        out: list[HookSite] = []
        for resource in await self._agents.list():
            try:
                cfg = AgentConfig.model_validate(resource.config)
            except Exception:
                continue
            adapter = self._catalog.delivery_hook(cfg.type)
            if adapter is None:
                continue
            out.append(HookSite(resource, adapter, self._spec(cfg, adapter).path))
        return out

    def installed_command(self, site: HookSite) -> str | None:
        """The command Coffer's marker-scoped entry carries in `site`'s file,
        or `None` when there is none. Raises `MalformedDeliveryConfig`, with
        the path, for a file it cannot parse. Writes nothing."""
        text = self._store.read_text(site.path) or ""
        try:
            return site.adapter.find_command(text)
        except MalformedDeliveryConfig as e:
            raise MalformedDeliveryConfig(f"{site.path}: {e}") from e

    async def write_install(self, agent_uid: str) -> DeliveryWrite:
        """Write Coffer's hook for one agent, replacing a prior entry in place,
        and return the edit. Does not audit — `install` does, and so does the
        reconciler for a repair.

        The uid is what goes into the installed command, so the entry keeps
        naming this agent however the user relabels it afterwards — and a
        rename costs no reinstall, which is the point of installing an identity
        rather than a label."""
        agent, cfg = await self._agent(agent_uid)
        adapter = self._adapter(cfg.type)
        spec = self._spec(cfg, adapter)
        prior = self._store.read_text(spec.path)
        new_text = self._with_path(spec, adapter.install, prior or "", agent.uid)
        assert new_text is not None  # install() always returns text, never None
        self._store.write_text_atomic(spec.path, new_text)
        return DeliveryWrite(agent, adapter.event, spec.path, prior, new_text)

    async def write_remove(self, agent_uid: str) -> DeliveryWrite | None:
        """Take only Coffer's entry out of one agent's file and return the
        edit; `None`, with nothing written, when no entry is there. Does not
        audit."""
        agent, cfg = await self._agent(agent_uid)
        adapter = self._adapter(cfg.type)
        spec = self._spec(cfg, adapter)
        prior = self._store.read_text(spec.path)
        text = prior or ""
        if self._with_path(spec, adapter.find_command, text) is None:
            return None
        new_text = self._with_path(spec, adapter.remove, text)
        assert new_text is not None  # remove() always returns text, never None
        self._store.write_text_atomic(spec.path, new_text)
        return DeliveryWrite(agent, adapter.event, spec.path, prior, new_text)

    def restore(self, write: DeliveryWrite) -> None:
        """Put back what `write` replaced — or remove the file it created."""
        if write.prior_text is None:
            self._store.delete_with_backup(write.path)
        else:
            self._store.write_text_atomic(write.path, write.prior_text)

    async def install(self, agent_uid: str, *, actor: str) -> DeliveryStatus:
        """Install Coffer's hook for one agent. Idempotent: a prior install is
        replaced in place, never duplicated. Always audited with `actor`."""
        write = await self.write_install(agent_uid)
        await self._audit.record(
            AuditEventType.MEMORY_DELIVERY_INSTALLED.value,
            resource=write.agent,
            actor=actor,
            details=write.details,
        )
        return await self.status(agent_uid)

    async def remove(self, agent_uid: str, *, actor: str) -> DeliveryStatus:
        """Remove Coffer's hook for one agent. A clean no-op — no write, no
        audit entry — when nothing is installed."""
        write = await self.write_remove(agent_uid)
        if write is not None:
            await self._audit.record(
                AuditEventType.MEMORY_DELIVERY_REMOVED.value,
                resource=write.agent,
                actor=actor,
                details=write.details,
            )
        return await self.status(agent_uid)

    async def record_fired(self, agent_uid: str) -> None:
        """Record that an agent's hook just fired (spec memory "Audit every delivery fire").

        Called by whatever actually serves the context — never by
        `install()`, `status()`, or anything else in this class — so every
        audited fire is a real one. The uid arrives from the installed command
        itself (`--agent-uid`), and it is resolved to a row here rather than
        recorded raw: an audit entry that named only a uid would be unreadable,
        and the row is what ties the fire to the agent's history.

        The actor is the agent, by the name it answers to now: nobody clicked
        anything, the hook ran because that agent started a session.
        """
        agent = await self._agents.get(agent_uid)
        await self._audit.record(
            AuditEventType.MEMORY_DELIVERY_FIRED.value,
            resource=agent,
            actor=agent.name,
        )

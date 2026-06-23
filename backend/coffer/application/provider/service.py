"""``ProviderService`` — CRUD, switch (activate) and key resolution for
provider profiles (spec 011).

A profile is stored as a ``provider`` resource (CRUD + audit + sync come free
from ``ResourceService``). This service adds the credential-vault handling, the
single-active-per-agent invariant, the native-config projection (the "switch",
chosen by the agent a connection is compatible with — not its wire), and the
per-connection key resolution used by Claude Code's ``apiKeyHelper``.

The credential store is synchronous (short-lived SQLite connections); every
call is wrapped in ``asyncio.to_thread`` so the busy-wait never blocks the loop
that holds the write lock (mirrors ``mcp_entry_service``).
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Awaitable, Callable
from typing import Protocol as _Protocol

from coffer.application.audit_service import AuditService
from coffer.application.provider.projector import ProviderProjector
from coffer.application.provider.results import ActivateResult, DeactivateResult
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.credential_errors import CredentialMissing
from coffer.domain.provider.config import Protocol, ProviderConfig, ResolvedConnection
from coffer.domain.provider.errors import NoActiveProvider, ProviderCredentialSourceInvalid
from coffer.domain.resource import Resource, ResourceRef

KIND = "provider"

# Module-scope alias: a bare ``list[AgentType]`` annotation on a method declared
# AFTER ``ProviderService.list`` would resolve ``list`` to that method (class-scope
# shadowing under PEP 563), so name the type here where ``list`` is the builtin.
_AgentTypes = list[AgentType]

# Maps a back-compat wire (the ``use-builtin/{wire}`` route, the legacy
# ``--wire`` key helper) to the agent it stands for. Activation, de-projection
# and key resolution are now keyed by AGENT type; this is the only place the old
# wire vocabulary is translated.
_AGENT_FOR_WIRE: dict[Protocol, AgentType] = {
    Protocol.ANTHROPIC: AgentType.CLAUDE_CODE,
    Protocol.OPENAI: AgentType.CODEX,
}


class _CredentialStore(_Protocol):
    def get(self, ref: str) -> str | None: ...
    def set(self, ref: str, value: str) -> None: ...
    def delete(self, ref: str) -> None: ...


class _ConfigFileStore(_Protocol):
    def read_text(self, path: pathlib.Path) -> str | None: ...
    def write_text_atomic(self, path: pathlib.Path, text: str) -> None: ...


class _AgentLister(_Protocol):
    async def list(self) -> list[Resource]: ...


class ProviderService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        credentials: _CredentialStore,
        config_store: _ConfigFileStore,
        agents: _AgentLister,
        audit: AuditService,
        resolve_internal_model: Callable[[], Awaitable[str | None]] | None = None,
    ) -> None:
        self._resources = resources
        self._credentials = credentials
        self._agents = agents
        self._audit = audit
        self._projector = ProviderProjector(config_store)
        # Resolves the internal-engine model (spec 011 E3), overlaid onto the
        # internal_default connection. None ⇒ no overlay (connection's own model).
        self._resolve_internal_model = resolve_internal_model

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _owned_ref(name: str) -> str:
        """The credential ref this service mints when a profile is created with
        an inline secret (``provider/<name>/key``)."""
        return f"provider/{name}/key"

    def _ref(self, name: str) -> ResourceRef:
        return ResourceRef(KIND, name)

    @staticmethod
    def _cfg(resource: Resource) -> ProviderConfig:
        return ProviderConfig.model_validate(resource.config)

    @staticmethod
    def _compat(cfg: ProviderConfig) -> list[AgentType]:
        """Hydrate the connection's resolved compatible-agent value strings into
        ``AgentType`` — the projection seam where the agent kind enters (the
        config itself stays agent-free for the cross-kind import contract)."""
        return [AgentType(a) for a in cfg.resolved_compatible_agents()]

    # --- CRUD ----------------------------------------------------------------

    async def create(
        self,
        name: str,
        *,
        protocol: Protocol,
        base_url: str,
        secret_value: str | None = None,
        credential_ref: str | None = None,
        compatible_agents: _AgentTypes | None = None,
        description: str | None = None,
        actor: str = "api",
    ) -> Resource:
        """Create a connection. For anthropic/openai/unknown supply EXACTLY one
        of ``secret_value`` (stored to the vault under ``provider/<name>/key``)
        or ``credential_ref`` (reuse an existing vault entry). An ``ollama``
        connection has no key — supply neither. ``compatible_agents`` overrides
        the wire default for which agents the connection projects into (``None``
        ⇒ the default). The model lives apart from the connection (spec 011 E3)
        and is chosen at the point of use."""
        ref: str | None
        minted = False
        if protocol is Protocol.OLLAMA:
            if secret_value is not None or credential_ref is not None:
                raise ProviderCredentialSourceInvalid()
            ref = None
        else:
            if (secret_value is None) == (credential_ref is None):
                raise ProviderCredentialSourceInvalid()
            ref = credential_ref
            if secret_value is not None:
                ref = self._owned_ref(name)
                await asyncio.to_thread(self._credentials.set, ref, secret_value)
                minted = True
        config = ProviderConfig(
            protocol=protocol,
            base_url=base_url,
            credential_ref=ref,
            # Store AgentType members as their value strings (config is agent-free).
            compatible_agents=(
                [a.value for a in compatible_agents] if compatible_agents is not None else None
            ),
            is_active=False,
        )
        try:
            return await self._resources.register(
                KIND, name, config.model_dump(mode="json"), actor, description=description
            )
        except BaseException:
            # Don't orphan the just-minted secret if registration fails
            # (duplicate name, etc.).
            if minted and ref is not None:
                await asyncio.to_thread(self._credentials.delete, ref)
            raise

    async def list(self) -> list[Resource]:
        return await self._resources.list(kind=KIND)

    async def get(self, name: str) -> Resource:
        return await self._resources.get(self._ref(name))

    async def update(
        self,
        name: str,
        *,
        base_url: str | None = None,
        secret_value: str | None = None,
        compatible_agents: _AgentTypes | None = None,
        description: str | None = None,
        actor: str = "api",
    ) -> Resource:
        """Partial update. ``protocol`` / ``credential_ref`` are immutable
        (identity); change them by recreating. ``secret_value`` rotates the
        secret stored under the profile's existing ref. ``compatible_agents``
        re-targets which agents the connection projects into (it is mutable,
        unlike the wire). The model is not stored on the connection (spec 011
        E3). Re-activate afterwards to re-project under the new targets."""
        current = await self.get(name)
        config = dict(current.config)
        if base_url is not None:
            config["base_url"] = base_url
        if compatible_agents is not None:
            config["compatible_agents"] = [a.value for a in compatible_agents]
        # Re-validate so a bad edit is rejected before the rotation / DB write.
        validated = ProviderConfig.model_validate(config).model_dump(mode="json")
        if secret_value is not None:
            ref = config.get("credential_ref")
            if not ref:
                raise ProviderCredentialSourceInvalid()
            await asyncio.to_thread(self._credentials.set, str(ref), secret_value)
        return await self._resources.update_config(
            self._ref(name), validated, actor, description=description
        )

    async def delete(self, name: str, *, actor: str = "api") -> None:
        """Delete a profile; if it owns its credential (``provider/<name>/key``)
        and nothing else cites it, remove the vault entry too."""
        resource = await self.get(name)
        cfg = self._cfg(resource)
        await self._resources.delete(self._ref(name), actor)
        owned = self._owned_ref(name)
        if cfg.credential_ref == owned and not await self._resources.find_credential_citations(
            owned
        ):
            await asyncio.to_thread(self._credentials.delete, owned)

    # --- switch + key resolution --------------------------------------------

    async def activate(self, name: str, *, actor: str = "api") -> ActivateResult:
        """Make ``name`` the active connection for each of its compatible agents
        and project it into every enabled agent of those types.

        Projection happens BEFORE the ``is_active`` flip so a native-config write
        failure (e.g. an unwritable agent config dir) aborts the switch with the
        registry untouched. The invariant is at most one active connection PER
        AGENT TYPE: activating this one takes over the agents it covers from any
        previously-active connection, and de-projects that connection from the
        agents this one does NOT cover so no stale config is left behind.
        """
        resource = await self.get(name)
        cfg = self._cfg(resource)
        targets = self._compat(cfg)
        agents = await self._agents.list()

        # 1) Project first. ollama (no targets) is internal-only — projects to
        #    no agent. ``skipped`` lists compatible agents with no registered one.
        projected: list[str] = []
        for at in targets:
            projected.extend(self._projector.project_type(name, cfg, agents, at))
        covered = {at for at in targets if self._projector.agents_of_type(agents, at)}
        skipped = [at.value for at in targets if at not in covered]

        # 2) Flip activation: take over from any overlapping active connection,
        #    de-projecting it from the agents this one will not cover. The
        #    single-process daemon serialises the clear-then-set (ADR-032 / FR-011).
        mine = set(targets)
        previous: str | None = None
        for r in await self.list():
            if r.name == name:
                continue
            rc = self._cfg(r)
            other = set(self._compat(rc))
            if not rc.is_active or not (other & mine):
                continue
            for at in other - mine:
                self._projector.deproject_type(agents, at)
            await self._set_active(r, active=False, actor=actor)
            previous = r.name
        if not cfg.is_active:
            await self._set_active(resource, active=True, actor=actor)

        await self._audit.record(
            AuditEventType.PROVIDER_SWITCHED.value,
            ref=self._ref(name),
            actor=actor,
            details={
                "from": previous,
                "to": name,
                "protocol": cfg.protocol.value,
                "agents": projected,
            },
        )
        return ActivateResult(
            activated=name, protocol=cfg.protocol.value, projected=projected, skipped=skipped
        )

    async def deactivate(self, wire: Protocol, *, actor: str = "api") -> DeactivateResult:
        """Switch the agent behind ``wire`` (anthropic→Claude Code, openai→Codex)
        back to its built-in login: de-project Coffer's keys and clear the active
        connection's ``is_active``. A connection compatible with multiple agents
        is reverted as a unit (the single ``is_active`` flag is all-or-nothing).
        Idempotent; de-projects before the flip, mirroring :meth:`activate`."""
        agent_type = _AGENT_FOR_WIRE.get(wire)
        agents = await self._agents.list()
        deprojected: list[str] = []
        previous: str | None = None
        if agent_type is not None:
            deprojected = self._projector.deproject_type(agents, agent_type)
            for r in await self.list():
                rc = self._cfg(r)
                compat = self._compat(rc)
                if not rc.is_active or agent_type not in compat:
                    continue
                for at in compat:
                    if at is not agent_type:
                        self._projector.deproject_type(agents, at)
                await self._set_active(r, active=False, actor=actor)
                previous = r.name

        if previous is not None or deprojected:
            details = {"from": previous, "to": None, "protocol": wire.value, "agents": deprojected}
            ref = self._ref(previous) if previous else self._ref(wire.value)
            await self._audit.record(
                AuditEventType.PROVIDER_SWITCHED.value, ref=ref, actor=actor, details=details
            )
        return DeactivateResult(protocol=wire.value, deprojected=deprojected, previous=previous)

    async def resolve_connection_key(self, name: str) -> str:
        """The decrypted key of a SPECIFIC connection by name — what Claude
        Code's projected ``apiKeyHelper`` (``--connection <name>``) fetches, so
        the agent always reads exactly the activated connection's key. Raises
        ``NoActiveProvider`` for a keyless (ollama) connection."""
        return await self._key_of(self._cfg(await self.get(name)), label=name)

    async def resolve_active_key_for_agent(self, agent_type: AgentType) -> str:
        """The decrypted key of the connection currently active AND compatible
        with ``agent_type`` — Codex's ``COFFER_PROVIDER_KEY`` injection. Raises
        ``NoActiveProvider`` if none."""
        for r in await self.list():
            rc = self._cfg(r)
            if rc.is_active and agent_type in self._compat(rc):
                return await self._key_of(rc, label=agent_type.value)
        raise NoActiveProvider(agent_type.value)

    async def resolve_active_key(self, wire: Protocol) -> str:
        """Back-compat: the active key for a wire's agent (legacy ``--wire`` key
        helper / ``/active-key/{wire}``). Resolves by the connection active for
        the agent the wire stands for."""
        agent_type = _AGENT_FOR_WIRE.get(wire)
        if agent_type is None:
            raise NoActiveProvider(wire.value)
        return await self.resolve_active_key_for_agent(agent_type)

    async def _key_of(self, cfg: ProviderConfig, *, label: str) -> str:
        ref = cfg.credential_ref
        if ref is None:
            raise NoActiveProvider(label)
        value = await asyncio.to_thread(self._credentials.get, ref)
        if value is None:
            raise CredentialMissing(ref)
        return value

    async def set_internal_default(self, name: str, *, actor: str = "api") -> Resource:
        """Make ``name`` the global internal-engine default — the connection
        Coffer's own LLM engine uses. Clears the flag on every other connection
        first, then sets this one; the single-process daemon serialises the
        clear-then-set so it never interleaves (mirrors ``activate``)."""
        resource = await self.get(name)
        previous: str | None = None
        for r in await self.list():
            if r.name == name:
                continue
            rc = self._cfg(r)
            if rc.internal_default:
                await self._set_internal_default_flag(r, value=False, actor=actor)
                previous = r.name
        if not self._cfg(resource).internal_default:
            await self._set_internal_default_flag(resource, value=True, actor=actor)
        await self._audit.record(
            AuditEventType.PROVIDER_INTERNAL_DEFAULT_SET.value,
            ref=self._ref(name),
            actor=actor,
            details={"from": previous, "to": name},
        )
        return await self.get(name)

    async def resolve_internal_connection(self) -> ResolvedConnection | None:
        """The connection + model Coffer's internal LLM engine runs on: the
        ``internal_default`` connection paired with the global internal-engine
        model (spec 011 E3). ``None`` when no connection is marked OR no model is
        set — either way the internal engine is a clean no-op (the model no
        longer lives on the connection, so there is no fallback)."""
        model = await self._resolve_internal_model() if self._resolve_internal_model else None
        if not model:
            return None
        for r in await self.list():
            rc = self._cfg(r)
            if rc.internal_default:
                return ResolvedConnection(config=rc, model=model)
        return None

    # --- internals -----------------------------------------------------------

    async def _set_active(self, resource: Resource, *, active: bool, actor: str) -> None:
        config = dict(resource.config)
        config["is_active"] = active
        await self._resources.update_config(self._ref(resource.name), config, actor)

    async def _set_internal_default_flag(
        self, resource: Resource, *, value: bool, actor: str
    ) -> None:
        config = dict(resource.config)
        config["internal_default"] = value
        await self._resources.update_config(self._ref(resource.name), config, actor)

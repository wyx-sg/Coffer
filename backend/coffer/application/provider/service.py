"""``ProviderService`` — CRUD, switch (activate) and key resolution for
provider profiles (spec provider-switching).

A profile is stored as a ``provider`` resource (CRUD + audit + sync come free
from ``ResourceService``). This service adds the credential-vault handling, the
single-active-per-agent invariant, the native-config projection (the "switch",
chosen by the agents a connection's per-agent scope reaches — not its wire), and
the per-connection key resolution used by Claude Code's ``apiKeyHelper``.

The credential store is synchronous (short-lived SQLite connections); every
call is wrapped in ``asyncio.to_thread`` so the busy-wait never blocks the loop
that holds the write lock (mirrors ``mcp_entry_service``).
"""

from __future__ import annotations

import asyncio
from typing import Protocol as _Protocol
from uuid import uuid4

from coffer.application.audit_service import AuditService
from coffer.application.provider.internal_default_ops import (
    internal_default_connection as _internal_default_connection_op,
)
from coffer.application.provider.internal_default_ops import (
    set_internal_default as _set_internal_default_op,
)
from coffer.application.provider.ports import EngineNotifyPort
from coffer.application.provider.projector import ProjectionConfigStore, ProviderProjector
from coffer.application.provider.results import ActivateResult, DeactivateResult
from coffer.application.provider.switch_ops import AGENT_FOR_WIRE
from coffer.application.provider.switch_ops import activate as _activate_op
from coffer.application.provider.switch_ops import deactivate as _deactivate_op
from coffer.application.provider.targets import projection_targets
from coffer.application.provider.transcribe_default_ops import (
    set_transcribe_default as _set_transcribe_default_op,
)
from coffer.application.provider.transcribe_default_ops import (
    transcribe_connection as _transcribe_connection_op,
)
from coffer.application.provider.update_ops import update as _update_op
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.types import AgentType
from coffer.domain.credential_errors import CredentialMissing
from coffer.domain.errors import ResourceNotFound
from coffer.domain.provider.config import CuratedModel, Protocol, ProviderConfig, ResolvedConnection
from coffer.domain.provider.errors import NoActiveProvider, ProviderCredentialSourceInvalid
from coffer.domain.resource import Resource

KIND = "provider"

# Module-scope alias: a bare ``list[CuratedModel]`` annotation on a method declared
# AFTER ``ProviderService.list`` would resolve ``list`` to that method (class-scope
# shadowing under PEP 563), so name the type here where ``list`` is the builtin.
_CuratedModels = list[CuratedModel]


class _CredentialStore(_Protocol):
    def get(self, ref: str) -> str | None: ...
    def set(self, ref: str, value: str) -> None: ...
    def delete(self, ref: str) -> None: ...


class _AgentLister(_Protocol):
    async def list(self) -> list[Resource]: ...


class ProviderService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        credentials: _CredentialStore,
        # Handed straight to the projector, so it is annotated with the
        # projector's own port rather than a second copy of it here.
        config_store: ProjectionConfigStore,
        agents: _AgentLister,
        audit: AuditService,
        engine: EngineNotifyPort | None = None,
    ) -> None:
        self._resources = resources
        self._credentials = credentials
        self._agents = agents
        self._audit = audit
        self._projector = ProviderProjector(config_store)
        # Coffer's internal engine, told when the connection it runs on moves (spec
        # internal-engine "Drop the engine model when its connection moves"). The
        # engine's model is not this kind's to reason about, so what happens to it
        # arrives as a port the composition root satisfies; ``None`` is the
        # test-convenience construction, where there is no engine to tell.
        self._engine = engine

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _mint_ref() -> str:
        """A fresh vault address for a profile created with an inline secret.

        Deliberately opaque rather than ``provider/<name>/key``: a ref is an
        ADDRESS, and deriving it from the connection's name made the name a key
        — renaming then had to move the secret, in an order chosen so a live
        agent never saw a missing one. Nothing reads the ref's shape; ownership
        is decided by citation (``release_orphaned_credentials``), not by the
        ref matching the name. Refs already minted under the old shape keep
        working untouched: they are just strings this config happens to hold.
        """
        return f"provider/{uuid4().hex}/key"

    @staticmethod
    def _cfg(resource: Resource) -> ProviderConfig:
        return ProviderConfig.model_validate(resource.config)

    @classmethod
    def _compat(cls, resource: Resource, agents: list[Resource]) -> list[AgentType]:
        """The agent types this connection projects into — its framework-level
        scope, hydrated at the projection seam (ADR per-agent-resource-scope).
        A disabled or keyless connection projects into nothing.

        ``agents`` is the registry the scope's uids are resolved against; every
        caller here has already listed it for the projection itself, so this
        adds no read."""
        return projection_targets(resource, cls._cfg(resource), agents)

    # --- CRUD ----------------------------------------------------------------

    async def create(
        self,
        name: str,
        *,
        protocol: Protocol,
        base_url: str,
        secret_value: str | None = None,
        credential_ref: str | None = None,
        models: _CuratedModels | None = None,
        description: str | None = None,
        actor: str = "api",
    ) -> Resource:
        """Create a connection. For anthropic/openai/unknown supply EXACTLY one
        of ``secret_value`` (stored to the vault at a freshly minted opaque ref
        — see :meth:`_mint_ref`) or ``credential_ref`` (reuse an existing vault
        entry). An ``ollama``
        connection has no key — supply neither. WHICH agents the connection
        projects into is its per-agent scope, started off by the kind (dormant
        for a keyless wire, unscoped otherwise) and edited afterwards through
        the framework's scope surface. The model lives apart from
        the connection (spec provider-switching "Take projected model keys from
        the agent's binding") and is chosen at the point of use;
        ``models`` only curates WHICH of the endpoint's models that choice is
        offered (``None``/empty ⇒ all of them)."""
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
                ref = self._mint_ref()
                await asyncio.to_thread(self._credentials.set, ref, secret_value)
                minted = True
        config = ProviderConfig(
            protocol=protocol,
            base_url=base_url,
            credential_ref=ref,
            models=list(models or []),
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

    async def get(self, uid: str) -> Resource:
        """One connection, by the identity every caller inside the daemon holds.

        A surface that started from a name the user typed resolves it once
        (``ResourceService.get_by_name``) and passes the uid in; nothing here
        takes a label. The kind is re-checked because a uid is opaque: a uid
        belonging to a skill would otherwise be handed to this service as a
        connection and fail somewhere further in, where the error no longer says
        what the caller actually got wrong. ``ResourceRef(KIND, name)`` used to
        carry that guarantee in its shape.
        """
        resource = await self._resources.get(uid)
        if resource.kind != KIND:
            raise ResourceNotFound(uid)
        return resource

    async def update(
        self,
        uid: str,
        *,
        protocol: Protocol | None = None,
        base_url: str | None = None,
        secret_value: str | None = None,
        models: _CuratedModels | None = None,
        description: str | None = None,
        actor: str = "api",
    ) -> Resource:
        """Partial update; see ``update_ops`` for what may move and what may not."""
        return await _update_op(
            self,
            uid,
            protocol=protocol,
            base_url=base_url,
            secret_value=secret_value,
            models=models,
            description=description,
            actor=actor,
        )

    async def delete(self, uid: str, *, actor: str = "api") -> None:
        """Delete a profile.

        The credential goes with it when nothing else cites it — but that is
        ``ResourceService.delete``'s job, not this one's: the kind declares a
        ``credential_ref_extractor``, so the generic path already releases the
        cited ref by citation count. This used to repeat that check here by
        asking whether the ref matched ``provider/<name>/key``, which only ever
        worked for refs whose shape spelled the name out.
        """
        await self.get(uid)  # 404 (and the kind check) before anything is removed
        await self._resources.delete(uid, actor)

    # There is deliberately no ``rename`` here. This kind had the only one in
    # Coffer, and it existed because the connection's NAME was written into
    # another tool's config file — Claude Code's ``apiKeyHelper`` shelled out
    # to ``--connection <name>``, so moving the label meant re-projecting or
    # leaving the agent calling something that no longer resolved. The helper
    # carries the uid now (``anthropic_api_key_helper``), so a rename writes one
    # column and nothing else: ``ResourceService.rename`` does that for every
    # kind, validating the name and refusing a collision in the one place those
    # rules live.

    # --- switch + key resolution --------------------------------------------

    async def activate(self, uid: str, *, actor: str = "api") -> ActivateResult:
        """Make this the active connection for each agent its scope reaches
        and project it into every enabled agent of those types.

        Projection happens BEFORE the ``is_active`` flip so a native-config write
        failure (e.g. an unwritable agent config dir) aborts the switch with the
        registry untouched. The invariant is at most one active connection PER
        AGENT TYPE: activating this one takes over the agents it covers from any
        previously-active connection, and de-projects that connection from the
        agents this one does NOT cover so no stale config is left behind. A thin
        delegate; the order of operations lives in ``switch_ops``.
        """
        return await _activate_op(self, uid, actor=actor)

    async def deactivate(self, wire: Protocol, *, actor: str = "api") -> DeactivateResult:
        """Switch the agent behind ``wire`` (anthropic→Claude Code, openai→Codex)
        back to its built-in login: de-project Coffer's keys and clear the active
        connection's ``is_active``. A connection reaching multiple agents
        is reverted as a unit (the single ``is_active`` flag is all-or-nothing).
        Idempotent; de-projects before the flip, mirroring :meth:`activate`."""
        return await _deactivate_op(self, wire, actor=actor)

    async def resolve_connection_key(self, uid: str) -> str:
        """The decrypted key of ONE specific connection — what Claude Code's
        projected ``apiKeyHelper`` (``/abs/path/to/coffer provider key
        --connection-uid <uid>``) fetches, so the agent always reads exactly the activated
        connection's key.

        By uid because that helper line is written once into a file Coffer does
        not own and then read on every turn, for as long as the connection
        lives: a name in it would stop resolving the moment the user renamed
        the connection.

        Raises ``NoActiveProvider`` when the connection reaches no agent — it is
        disabled, scoped to no agent, or keyless (ollama). Reach is the same
        effective projection the wire form reads (``projection_targets``), so a
        live helper line stops receiving the key the moment the user switches
        the connection off (spec provider-switching "Resolve a key for exactly
        one connection").
        """
        resource = await self.get(uid)
        cfg = self._cfg(resource)
        if not self._compat(resource, await self._agents.list()):
            raise NoActiveProvider(resource.name)
        return await self._key_of(cfg, label=resource.name)

    async def resolve_active_key_for_agent(self, agent_type: AgentType) -> str:
        """The decrypted key of the connection currently active AND reaching
        ``agent_type`` (its scope, ∩ ``enabled``) — Codex's
        ``COFFER_PROVIDER_KEY`` injection. Raises ``NoActiveProvider`` if none."""
        agents = await self._agents.list()
        for r in await self.list():
            rc = self._cfg(r)
            if rc.is_active and agent_type in self._compat(r, agents):
                return await self._key_of(rc, label=agent_type.value)
        raise NoActiveProvider(agent_type.value)

    async def resolve_active_key(self, wire: Protocol) -> str:
        """Back-compat: the active key for a wire's agent (legacy ``--wire`` key
        helper / ``/active-key/{wire}``). Resolves by the connection active for
        the agent the wire stands for."""
        agent_type = AGENT_FOR_WIRE.get(wire)
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

    async def set_internal_default(self, uid: str, *, actor: str = "api") -> Resource:
        """Make this the global internal-engine default — the connection
        Coffer's own LLM engine uses.

        A thin delegate: the flag's single-global invariant and the fate of the
        internal-engine model when the connection moves both live in
        ``internal_default_ops``, so BOTH callers — the HTTP route and
        ``coffer provider internal-default`` — get them.
        """
        return await _set_internal_default_op(self, uid, actor=actor)

    async def internal_default_connection(self, model: str) -> ResolvedConnection | None:
        """The connection marked ``internal_default``, paired with ``model``.

        Satisfies ``application.engine.resolve.InternalDefaultConnectionPort``.
        """
        return await _internal_default_connection_op(self, model)

    async def set_transcribe_default(self, uid: str, *, actor: str = "api") -> Resource:
        """Make this the global speech-to-text connection.

        The twin of :meth:`set_internal_default`, delegating for the same
        reason: the single-global invariant and the fate of the transcription
        model when the connection moves belong to both callers, the HTTP route
        and ``coffer provider transcribe-default``.
        """
        return await _set_transcribe_default_op(self, uid, actor=actor)

    async def transcribe_connection(self, model: str) -> ResolvedConnection | None:
        """The connection marked ``transcribe_default``, paired with ``model``.

        Satisfies ``application.engine.resolve.TranscribeConnectionPort``.
        """
        return await _transcribe_connection_op(self, model)

    # --- internals -----------------------------------------------------------

    async def _set_active(self, resource: Resource, *, active: bool, actor: str) -> None:
        config = dict(resource.config)
        config["is_active"] = active
        await self._resources.update_config(resource.uid, config, actor)

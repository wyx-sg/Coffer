"""``ProviderService`` — CRUD, switch (activate) and key resolution for
provider profiles (spec provider-switching).

A profile is stored as a ``provider`` resource (CRUD + audit + sync come free
from ``ResourceService``). This service adds the secret-vault handling, the
per-agent switch (which connection an agent runs on is a field of the agent's own
record), the native-config projection it writes (the agent's file, chosen by the
agent — not by the connection's wire), and the key decryption the model proxy's
state is built from — no route returns a key; the proxy injects it (ADR
api-key-providers-are-reached-through-a-separate-local-model-proxy).

The secret store is synchronous (``.enc`` files under the vault); every call
is wrapped in ``asyncio.to_thread`` so file I/O never blocks the event loop
(mirrors ``mcp_entry_service``).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import Protocol as _Protocol

from coffer.application.audit_service import AuditService
from coffer.application.provider.delete_ops import delete as _delete_op
from coffer.application.provider.delete_ops import preview as _delete_preview_op
from coffer.application.provider.internal_default_ops import (
    internal_default_connection as _internal_default_connection_op,
)
from coffer.application.provider.internal_default_ops import (
    set_internal_default as _set_internal_default_op,
)
from coffer.application.provider.ports import EngineNotifyPort
from coffer.application.provider.projector import ProjectionConfigStore, ProviderProjector
from coffer.application.provider.results import ActivateResult, DeactivateResult, DeletePreview
from coffer.application.provider.secret_gate import ProviderSecretBoundary, require_key
from coffer.application.provider.switch_ops import activate as _activate_op
from coffer.application.provider.switch_ops import deactivate as _deactivate_op
from coffer.application.provider.transcribe_default_ops import (
    set_transcribe_default as _set_transcribe_default_op,
)
from coffer.application.provider.transcribe_default_ops import (
    transcribe_connection as _transcribe_connection_op,
)
from coffer.application.provider.update_ops import update as _update_op
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.provider.config import CuratedModel, Protocol, ProviderConfig, ResolvedConnection
from coffer.domain.provider.errors import ProviderSecretSourceInvalid
from coffer.domain.provider.local_runtime import LocalRuntime
from coffer.domain.resource import Resource
from coffer.domain.secret_errors import SecretMissing
from coffer.domain.secrets import resource_secret_ref

KIND = "provider"

# Module-scope alias: a bare ``list[CuratedModel]`` annotation on a method declared
# AFTER ``ProviderService.list`` would resolve ``list`` to that method (class-scope
# shadowing under PEP 563), so name the type here where ``list`` is the builtin.
_CuratedModels = list[CuratedModel]
_Uids = list[str]
_Rows = list[Resource]


class _SecretStore(_Protocol):
    def get(self, ref: str) -> str | None: ...
    def exists(self, ref: str) -> bool: ...
    def set(self, ref: str, value: str) -> None: ...
    def delete(self, ref: str) -> None: ...


class _AgentRegistry(_Protocol):
    """The agent kind, as this one needs it: the rows, and the one field of an
    agent's record a switch writes."""

    async def list(self) -> list[Resource]: ...
    async def set_connection(
        self, uid: str, connection_uid: str | None, *, actor: str = "api"
    ) -> Resource: ...


class ProviderService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        secrets: _SecretStore,
        # Handed straight to the projector, so it is annotated with the
        # projector's own port rather than a second copy of it here.
        config_store: ProjectionConfigStore,
        agents: _AgentRegistry,
        audit: AuditService,
        agent_catalog: AgentCatalog,
        engine: EngineNotifyPort | None = None,
        hold: Callable[[], contextlib.AbstractAsyncContextManager[object]] | None = None,
        proxy_root: Callable[[], str] | None = None,
    ) -> None:
        self._resources = resources
        self._secrets = secrets
        self._agents = agents
        self._audit = audit
        # The agents' provider projection facets: what each agent's native
        # config speaks and how a connection is written into it.
        self._catalog = agent_catalog
        # Where the local model proxy listens, for the base URL the agents
        # are pointed at; the projector's default when not given.
        self._projector = (
            ProviderProjector(config_store, agents=agent_catalog, proxy_root=proxy_root)
            if proxy_root is not None
            else ProviderProjector(config_store, agents=agent_catalog)
        )
        # Coffer's internal engine, told when the connection it runs on moves (spec
        # internal-engine "Drop the engine model when its connection moves"). The
        # engine's model is not this kind's to reason about, so what happens to it
        # arrives as a port the composition root satisfies; ``None`` is the
        # test-convenience construction, where there is no engine to tell.
        self._engine = engine
        # The reconciler's hold: a switch is several writes (project, then move
        # the flags), and no periodic pass may judge the state in between.
        # Re-entrant inside a pass, so a repair that switches cannot deadlock.
        self._hold = hold or contextlib.nullcontext
        # The secret boundary (``secret_gate``), set by the composition root.
        self._boundary: ProviderSecretBoundary | None = None

    def set_secret_boundary(self, boundary: ProviderSecretBoundary) -> None:
        self._boundary = boundary

    # --- helpers -------------------------------------------------------------

    async def _mint_ref(self, name: str) -> str:
        """A fresh vault address for a profile created with an inline secret:
        ``provider/<name>/key``, with ``-2``, ``-3``… on the name while the
        ref is stored or cited by something (spec secret "Name a resource's
        secret after the resource and its slot"). Renaming the connection
        moves it (``application.secret.ref_names``); ownership is decided by
        citation (``release_orphaned_secrets``)."""
        cited = set(await self._resources.cited_secret_refs())
        n = 1
        while True:
            ref = resource_secret_ref(KIND, name if n == 1 else f"{name}-{n}", "key")
            if ref not in cited and not await asyncio.to_thread(self._secrets.exists, ref):
                return ref
            n += 1

    @staticmethod
    def _cfg(resource: Resource) -> ProviderConfig:
        return ProviderConfig.model_validate(resource.config)

    # --- CRUD ----------------------------------------------------------------

    async def create(
        self,
        name: str,
        *,
        protocol: Protocol,
        base_url: str,
        secret_value: str | None = None,
        secret_ref: str | None = None,
        models: _CuratedModels | None = None,
        description: str | None = None,
        local_runtime: LocalRuntime | None = None,
        actor: str = "api",
    ) -> Resource:
        """Create a connection. A local runtime (``local_runtime``, what
        detection found at a loopback endpoint) may carry a key or none.
        Otherwise, for anthropic/openai/unknown supply EXACTLY one
        of ``secret_value`` (stored to the vault at a ref named for the connection
        — see :meth:`_mint_ref`) or ``secret_ref`` (reuse an existing vault
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
            if secret_value is not None or secret_ref is not None:
                raise ProviderSecretSourceInvalid()
            ref = None
        elif local_runtime is not None and secret_value is None and secret_ref is None:
            ref = None
        else:
            if (secret_value is None) == (secret_ref is None):
                raise ProviderSecretSourceInvalid()
            ref = secret_ref
            if secret_value is not None:
                ref = await self._mint_ref(name)
                await asyncio.to_thread(self._secrets.set, ref, secret_value)
                minted = True
        config = ProviderConfig(
            protocol=protocol,
            base_url=base_url,
            secret_ref=ref,
            models=list(models or []),
            local_runtime=local_runtime,
        )
        try:
            return await self._resources.register(
                KIND, name, config.model_dump(mode="json"), actor, description=description
            )
        except BaseException:
            # Don't orphan the just-minted secret if registration fails
            # (duplicate name, etc.).
            if minted and ref is not None:
                await asyncio.to_thread(self._secrets.delete, ref)
            raise

    async def list(self) -> list[Resource]:
        """Every connection, by name (case-insensitive)."""
        rows = await self._resources.list(kind=KIND)
        return sorted(rows, key=lambda r: (r.name.lower(), r.name))

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

        The secret goes with it when nothing else cites it — but that is
        ``ResourceService.delete``'s job, not this one's: the kind declares a
        ``secret_ref_extractor``, so the generic path already releases the
        cited ref by citation count. Agents that run on the profile are first put
        back on their built-in login (``delete_ops``); a refused de-projection
        keeps the profile.
        """
        await _delete_op(self, uid, actor=actor)

    async def delete_preview(self, uid: str) -> DeletePreview:
        """What deleting this profile would change in the agents running on it
        (their config files, with diffs); writes nothing."""
        return await _delete_preview_op(self, uid)

    # There is deliberately no ``rename`` here. This kind had the only one in
    # Coffer, and it existed because the connection's NAME was written into
    # another tool's config file — Claude Code's ``apiKeyHelper`` shelled out
    # to ``--connection <name>``, so moving the label meant re-projecting or
    # leaving the agent calling something that no longer resolved. What Coffer
    # writes now names no connection at all — the helper prints the agent's
    # local proxy token (``proxy_token_helper``, keyed by the agent's uid) — so
    # a rename writes one column and nothing else: ``ResourceService.rename`` does that for every
    # kind, validating the name and refusing a collision in the one place those
    # rules live.

    # --- switch ----------------------------------------------------------------

    async def activate(
        self, uid: str, agent_type: AgentType, *, actor: str = "api"
    ) -> ActivateResult:
        """Switch the agent of ``agent_type`` onto this connection: project it
        into that agent's native config and record it as the agent's connection.

        Per agent: nothing else changes (spec provider-switching "Switch one
        agent at a time"). Projection happens BEFORE the record is written so a
        native-config write failure (an unwritable config dir, a file the user
        edited under us) aborts the switch with the registry untouched, and a
        failure after it puts the file back. A thin delegate; the order of
        operations lives in ``switch_ops``.
        """
        async with self._hold():
            return await _activate_op(self, uid, agent_type, actor=actor)

    async def deactivate(self, agent_type: AgentType, *, actor: str = "api") -> DeactivateResult:
        """Switch the agent of ``agent_type`` back to its built-in login:
        de-project Coffer's keys and clear its connection. Idempotent;
        de-projects before the record is written, mirroring :meth:`activate`."""
        async with self._hold():
            return await _deactivate_op(self, agent_type, actor=actor)

    async def clear_agent_connection(self, agent_uid: str, *, actor: str = "system") -> None:
        """Clear one agent's connection and write nothing else: the reconciler's
        way of dropping a choice the agent's config contradicts (no file is
        touched, the record is Coffer's own)."""
        async with self._hold():
            await self._agents.set_connection(agent_uid, None, actor=actor)

    async def _key_of(self, cfg: ProviderConfig, *, label: str, uid: str) -> str:
        """The decrypted key of one connection, for the model proxy's state —
        only once its base URL is an approved destination (``secret_gate``)."""
        ref = cfg.secret_ref
        assert ref is not None, "the proxy state asks for a key only of a keyed connection"
        await require_key(self, uid, label, cfg)
        value = await asyncio.to_thread(self._secrets.get, ref)
        if value is None:
            raise SecretMissing(ref)
        return value

    async def set_internal_default(self, uid: str, *, actor: str = "api") -> Resource:
        """Make this the global internal-engine default — the connection
        Coffer's own LLM engine uses.

        A thin delegate: the flag's single-global invariant and the fate of the
        internal-engine model when the connection moves both live in
        ``internal_default_ops``, so BOTH callers — the HTTP route and
        the Settings page's engine choice — get them.
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
        and the Settings page's transcription choice.
        """
        return await _set_transcribe_default_op(self, uid, actor=actor)

    async def transcribe_connection(self, model: str) -> ResolvedConnection | None:
        """The connection marked ``transcribe_default``, paired with ``model``.

        Satisfies ``application.engine.resolve.TranscribeConnectionPort``.
        """
        return await _transcribe_connection_op(self, model)

"""``ProviderService`` — CRUD, switch (activate) and key resolution for
provider profiles (spec 011).

A profile is stored as a ``provider`` resource (CRUD + audit + sync come free
from ``ResourceService``). This service adds the credential-vault handling, the
single-active-per-wire invariant, the native-config projection (the "switch"),
and the key resolution used by Claude Code's ``apiKeyHelper``.

The credential store is synchronous (short-lived SQLite connections); every
call is wrapped in ``asyncio.to_thread`` so the busy-wait never blocks the loop
that holds the write lock (mirrors ``mcp_entry_service``).
"""

from __future__ import annotations

import asyncio
import pathlib
from dataclasses import dataclass
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.config_files import spec_for
from coffer.domain.audit import AuditEventType
from coffer.domain.credential_errors import CredentialMissing
from coffer.domain.provider.config import ProviderConfig, WireApi, WireFormat
from coffer.domain.provider.errors import NoActiveProvider, ProviderCredentialSourceInvalid
from coffer.domain.provider.projection import (
    apply_anthropic_settings,
    apply_codex_provider,
    target_for,
)
from coffer.domain.resource import Resource, ResourceRef

KIND = "provider"


class _CredentialStore(Protocol):
    def get(self, ref: str) -> str | None: ...
    def set(self, ref: str, value: str) -> None: ...
    def delete(self, ref: str) -> None: ...


class _ConfigFileStore(Protocol):
    def read_text(self, path: pathlib.Path) -> str | None: ...
    def write_text_atomic(self, path: pathlib.Path, text: str) -> None: ...


class _AgentLister(Protocol):
    async def list(self) -> list[Resource]: ...


@dataclass(frozen=True)
class ActivateResult:
    """Outcome of a switch: which agents were written, which wire had none."""

    activated: str
    wire_format: str
    projected: list[str]
    skipped: list[str]


class ProviderService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        credentials: _CredentialStore,
        config_store: _ConfigFileStore,
        agents: _AgentLister,
        audit: AuditService,
    ) -> None:
        self._resources = resources
        self._credentials = credentials
        self._config_store = config_store
        self._agents = agents
        self._audit = audit

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

    # --- CRUD ----------------------------------------------------------------

    async def create(
        self,
        name: str,
        *,
        wire_format: WireFormat,
        base_url: str,
        model: str,
        fast_model: str | None = None,
        wire_api: WireApi = WireApi.RESPONSES,
        secret_value: str | None = None,
        credential_ref: str | None = None,
        description: str | None = None,
        actor: str = "api",
    ) -> Resource:
        """Create a connection. For anthropic/openai supply EXACTLY one of
        ``secret_value`` (stored to the vault under ``provider/<name>/key``) or
        ``credential_ref`` (reuse an existing vault entry). An ``ollama``
        connection has no key — supply neither."""
        ref: str | None
        minted = False
        if wire_format is WireFormat.OLLAMA:
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
            wire_format=wire_format,
            base_url=base_url,
            credential_ref=ref,
            model=model,
            fast_model=fast_model,
            wire_api=wire_api,
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
        model: str | None = None,
        fast_model: str | None = None,
        clear_fast_model: bool = False,
        wire_api: WireApi | None = None,
        secret_value: str | None = None,
        description: str | None = None,
        actor: str = "api",
    ) -> Resource:
        """Partial update. ``wire_format`` / ``credential_ref`` are immutable
        (identity); change them by recreating. ``secret_value`` rotates the
        secret stored under the profile's existing ref."""
        current = await self.get(name)
        config = dict(current.config)
        if base_url is not None:
            config["base_url"] = base_url
        if model is not None:
            config["model"] = model
        if clear_fast_model:
            config["fast_model"] = None
        elif fast_model is not None:
            config["fast_model"] = fast_model
        if wire_api is not None:
            config["wire_api"] = wire_api.value
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
        """Make ``name`` the active profile for its wire format and project it
        into every enabled agent of the matching type.

        Projection happens BEFORE the ``is_active`` flip so a native-config
        write failure (e.g. an unwritable agent config dir) aborts the switch
        with the registry untouched, rather than leaving a flipped flag with no
        matching on-disk config.
        """
        resource = await self.get(name)
        cfg = self._cfg(resource)
        wire = cfg.wire_format
        target = target_for(wire)

        # 1) Project first. A failure here raises before any state mutation.
        #    ollama (target is None) is internal-only — it projects to no agent.
        projected: list[str] = []
        if target is not None:
            for agent in await self._agents.list():
                if not agent.enabled:
                    continue
                if AgentConfig.model_validate(agent.config).type != target.agent_type:
                    continue
                self._project(name, cfg, agent, target.config_key)
                projected.append(agent.name)
        skipped = [] if projected else [target.agent_type.value if target else wire.value]

        # 2) Flip activation: clear other same-wire actives, then set this one.
        # Single-process daemon serializes requests, so the clear-then-set runs
        # without interleaving (see ADR-032 / FR-011).
        previous: str | None = None
        for r in await self.list():
            if r.name == name:
                continue
            rc = self._cfg(r)
            if rc.wire_format == wire and rc.is_active:
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
                "wire_format": wire.value,
                "agents": projected,
            },
        )
        return ActivateResult(
            activated=name, wire_format=wire.value, projected=projected, skipped=skipped
        )

    async def resolve_active_key(self, wire: WireFormat) -> str:
        """The decrypted API key of the active profile for ``wire`` (used by
        Claude's ``apiKeyHelper``). Raises ``NoActiveProvider`` if none."""
        for r in await self.list():
            rc = self._cfg(r)
            if rc.wire_format == wire and rc.is_active:
                ref = rc.credential_ref
                if ref is None:
                    raise NoActiveProvider(wire.value)
                value = await asyncio.to_thread(self._credentials.get, ref)
                if value is None:
                    raise CredentialMissing(ref)
                return value
        raise NoActiveProvider(wire.value)

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

    async def resolve_internal_connection(self) -> ProviderConfig | None:
        """The connection Coffer's internal LLM engine uses (the one flagged
        ``internal_default``), or ``None`` when none is configured — in which
        case the internal engine is a clean no-op."""
        for r in await self.list():
            rc = self._cfg(r)
            if rc.internal_default:
                return rc
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

    def _project(
        self, profile_name: str, cfg: ProviderConfig, agent: Resource, config_key: str
    ) -> None:
        agent_cfg = AgentConfig.model_validate(agent.config)
        spec = spec_for(agent_cfg.type, config_key, agent_cfg.resolved_config_dir())
        text = self._config_store.read_text(spec.path) or ""
        if cfg.wire_format == WireFormat.ANTHROPIC:
            new_text = apply_anthropic_settings(
                text, base_url=cfg.base_url, model=cfg.model, fast_model=cfg.fast_model
            )
        else:
            new_text = apply_codex_provider(
                text,
                base_url=cfg.base_url,
                model=cfg.model,
                wire_api=cfg.wire_api.value,
                display_name=f"Coffer ({profile_name})",
            )
        self._config_store.write_text_atomic(spec.path, new_text)

"""Kind-agnostic Resource CRUD service.

The service is constructed with a dict of registered kinds; it never
imports any kind-specific module. Each mutation is audited via
AuditService. `delete` calls the kind's optional `on_delete` hook
BEFORE persistence; a hook that raises aborts the deletion.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import ValidationError

from coffer.application.audit_service import AuditService
from coffer.application.repos import ResourceRepo
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    ConfigValidationError,
    CredentialMissing,
    GenericCreateNotAllowed,
    ResourceNotFound,
    UnknownKind,
)
from coffer.domain.resource import Kind, Resource, ResourceRef


class _KeyringPort(Protocol):
    """Minimal kind-agnostic port for register-time credential probing.

    Structurally compatible with :class:`coffer.application.mcp.ports.KeyringPort`
    but defined locally so the kind-agnostic resource service does not import
    the mcp-specific port module (importlinter Contract 6).
    """

    def get(self, ref: str) -> str | None: ...


def _audit_safe_config(kind_def: Kind, config: dict[str, Any]) -> dict[str, Any]:
    """Return an audit-safe copy of ``config`` using the kind's redactor.

    The kind-agnostic core knows nothing about where a given kind stores
    secrets; each kind supplies its own ``audit_redactor`` (e.g. mcp_server
    strips ``transport.env``/``headers``). Kinds without one audit their
    config verbatim. See ADR-001 / CODE-006.
    """
    if kind_def.audit_redactor is None:
        return config
    return kind_def.audit_redactor(config)


def _extract_credential_refs(kind_def: Kind, config: dict[str, Any]) -> dict[str, str]:
    """Return ``{key: keychain_ref}`` for ``config`` using the kind's extractor.

    Kinds without a ``credential_ref_extractor`` declare no credentials and are
    not probed.
    """
    if kind_def.credential_ref_extractor is None:
        return {}
    return kind_def.credential_ref_extractor(config)


class ResourceService:
    def __init__(
        self,
        kinds: dict[str, Kind],
        repo: ResourceRepo,
        audit: AuditService,
        keyring: _KeyringPort | None = None,
    ) -> None:
        self._kinds = kinds
        self._repo = repo
        self._audit = audit
        self._keyring = keyring

    def _probe_credentials(self, kind_def: Kind, config: dict[str, Any]) -> None:
        """Raise CredentialMissing if any cited credential_ref is absent.

        Called BEFORE persisting a Resource so a missing credential never
        leaves a partial row in the resources table. Skipped if no keyring
        is wired (back-compat for tests that don't need credential checks).
        """
        if self._keyring is None:
            return
        for _key, ref in _extract_credential_refs(kind_def, config).items():
            if self._keyring.get(ref) is None:
                raise CredentialMissing(ref)

    def _require_kind(self, kind: str) -> Kind:
        if kind not in self._kinds:
            raise UnknownKind(kind)
        return self._kinds[kind]

    def _validate_config(self, kind_def: Kind, config: dict[str, Any]) -> dict[str, Any]:
        try:
            validated = kind_def.config_schema.model_validate(config)
        except ValidationError as e:
            raise ConfigValidationError(str(e)) from e
        # mode='json' ensures Pydantic special types (e.g. HttpUrl) are
        # serialised to plain str rather than their Pydantic wrapper objects,
        # which are not JSON-serialisable by the standard library json module.
        return validated.model_dump(mode="json")

    async def register(
        self,
        kind: str,
        name: str,
        config: dict[str, Any],
        actor: str,
        description: str | None = None,
        *,
        allow_lifecycle_kind: bool = False,
    ) -> Resource:
        kind_def = self._require_kind(kind)
        # CODE-REG: a kind that owns creation invariants beyond config
        # validation (skill master folder, agent on-disk detection) sets
        # ``generic_create_allowed=False``. The generic POST /resources path
        # calls register() with the default ``allow_lifecycle_kind=False`` and
        # is rejected here, so it can never create a row with no backing
        # artifact; the kind's dedicated service opts in explicitly.
        if not kind_def.generic_create_allowed and not allow_lifecycle_kind:
            raise GenericCreateNotAllowed(kind)
        # CODE-030: kind-specific name validation BEFORE any DB write (e.g.
        # mcp_server reserves '__' as the tool/prompt namespace separator).
        if kind_def.validate_name is not None:
            try:
                kind_def.validate_name(name)
            except ValueError as e:
                raise ConfigValidationError(str(e)) from e
        validated = self._validate_config(kind_def, config)
        # Probe before any DB write — a missing credential must not leave a
        # half-created resource row behind. The spec's "credential missing"
        # edge case requires registration to fail naming the missing ref.
        self._probe_credentials(kind_def, validated)
        now = datetime.now(tz=UTC)
        created = await self._repo.create(
            Resource(
                id=0,
                kind=kind,
                name=name,
                description=description,
                config=validated,
                enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
        await self._audit.record(
            AuditEventType.RESOURCE_CREATED.value,
            ref=created.ref,
            actor=actor,
            details={"config": _audit_safe_config(kind_def, validated)},
        )
        return created

    async def list(
        self,
        kind: str | None = None,
        enabled: bool | None = None,
    ) -> list[Resource]:
        return await self._repo.list(kind=kind, enabled=enabled)

    async def get(self, ref: ResourceRef) -> Resource:
        r = await self._repo.find(ref)
        if r is None:
            raise ResourceNotFound(ref.kind, ref.name)
        return r

    async def update_config(
        self,
        ref: ResourceRef,
        new_config: dict[str, Any],
        actor: str,
        description: str | None = None,
        *,
        allow_lifecycle_kind: bool = False,
    ) -> Resource:
        kind_def = self._require_kind(ref.kind)
        # CODE-REG applies to updates too: a generic PATCH rewriting a
        # lifecycle kind's config (e.g. a skill's name) would desync the row
        # from the on-disk artifact its owning service maintains.
        if not kind_def.generic_create_allowed and not allow_lifecycle_kind:
            raise GenericCreateNotAllowed(ref.kind)
        validated = self._validate_config(kind_def, new_config)
        # Same register-time invariant: if the update introduces a credential
        # ref that does not exist in the keychain, fail before the DB write.
        self._probe_credentials(kind_def, validated)
        before = await self.get(ref)
        # Per-kind cross-version validation (e.g. ``knowledge_base`` enforces
        # ``embedding_model`` immutability — TEST22-021). Hook may raise
        # ``ConfigValidationError`` to reject the update before the DB write.
        if kind_def.on_update_config is not None:
            hook_result = kind_def.on_update_config(ref, before.config, validated)
            if inspect.isawaitable(hook_result):
                await hook_result
        updated = await self._repo.update_config(ref, validated, description)
        await self._audit.record(
            AuditEventType.RESOURCE_UPDATED.value,
            ref=ref,
            actor=actor,
            details={
                "before": _audit_safe_config(kind_def, before.config),
                "after": _audit_safe_config(kind_def, validated),
            },
        )
        return updated

    async def set_enabled(self, ref: ResourceRef, enabled: bool, actor: str) -> Resource:
        before = await self.get(ref)
        if before.enabled == enabled:
            return before  # idempotent — no audit
        updated = await self._repo.set_enabled(ref, enabled)
        event = AuditEventType.RESOURCE_ENABLED if enabled else AuditEventType.RESOURCE_DISABLED
        await self._audit.record(event.value, ref=ref, actor=actor)
        return updated

    async def delete(self, ref: ResourceRef, actor: str) -> None:
        kind_def = self._require_kind(ref.kind)
        snapshot = await self.get(ref)  # raises ResourceNotFound if missing
        if kind_def.on_delete is not None:
            # CODE-033: await an async on_delete hook so side effects (e.g.
            # evicting live upstream connections, tearing down skill symlinks)
            # COMPLETE before the row is removed. A sync hook still runs
            # synchronously. A hook that raises aborts the deletion (propagates
            # to the caller). Otherwise a follow-up read inside the hook would
            # hit ResourceNotFound and the cleanup would be silently dropped.
            result = kind_def.on_delete(ref)
            if inspect.isawaitable(result):
                await result
        await self._repo.delete(ref)
        await self._audit.record(
            AuditEventType.RESOURCE_DELETED.value,
            ref=ref,
            actor=actor,
            details={
                "snapshot": {
                    "kind": snapshot.kind,
                    "name": snapshot.name,
                    "config": _audit_safe_config(kind_def, snapshot.config),
                    "enabled": snapshot.enabled,
                }
            },
        )

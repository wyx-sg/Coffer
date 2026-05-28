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
    ResourceNotFound,
    UnknownKind,
)
from coffer.domain.resource import Kind, Resource, ResourceRef

# Keys inside ``transport`` whose values may carry auth material (custom
# headers, raw environment overlays). We persist credential_refs in audit
# (those are keychain ref strings only) but strip the raw maps. See CODE-006.
_AUDIT_STRIP_TRANSPORT_KEYS: frozenset[str] = frozenset({"env", "headers"})


class _KeyringPort(Protocol):
    """Minimal kind-agnostic port for register-time credential probing.

    Structurally compatible with :class:`coffer.application.mcp.ports.KeyringPort`
    but defined locally so the kind-agnostic resource service does not import
    the mcp-specific port module (importlinter Contract 6).
    """

    def get(self, ref: str) -> str | None: ...


def _audit_safe_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``config`` with auth-bearing keys stripped from transport.

    Why: clients can paste custom auth headers / env vars into MCP server
    config (e.g. an Authorization header on an HTTP transport). Those are
    materialised at spawn time from the keychain — but a careless user might
    paste the raw secret in instead, and we don't want it landing verbatim
    in audit_log.details_json. Stripping the structural maps keeps audit
    useful (credential_refs survive; users can still see *what* changed)
    without ever persisting the secret material itself.
    """
    transport = config.get("transport")
    if not isinstance(transport, dict):
        return config
    sanitised_transport = {
        k: v for k, v in transport.items() if k not in _AUDIT_STRIP_TRANSPORT_KEYS
    }
    return {**config, "transport": sanitised_transport}


def _extract_credential_refs(config: dict[str, Any]) -> dict[str, str]:
    """Pull `transport.credential_refs` out of a validated config dict.

    Kind-agnostic by shape: any config whose validated form has a
    `transport.credential_refs` mapping participates in register-time
    credential probing. Returns {} otherwise.
    """
    transport = config.get("transport")
    if not isinstance(transport, dict):
        return {}
    refs = transport.get("credential_refs")
    if not isinstance(refs, dict):
        return {}
    return {str(k): str(v) for k, v in refs.items()}


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

    def _probe_credentials(self, config: dict[str, Any]) -> None:
        """Raise CredentialMissing if any cited credential_ref is absent.

        Called BEFORE persisting a Resource so a missing credential never
        leaves a partial row in the resources table. Skipped if no keyring
        is wired (back-compat for tests that don't need credential checks).
        """
        if self._keyring is None:
            return
        for _key, ref in _extract_credential_refs(config).items():
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
    ) -> Resource:
        kind_def = self._require_kind(kind)
        validated = self._validate_config(kind_def, config)
        # Probe before any DB write — a missing credential must not leave a
        # half-created resource row behind. The spec's "credential missing"
        # edge case requires registration to fail naming the missing ref.
        self._probe_credentials(validated)
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
            details={"config": _audit_safe_config(validated)},
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
    ) -> Resource:
        kind_def = self._require_kind(ref.kind)
        validated = self._validate_config(kind_def, new_config)
        # Same register-time invariant: if the update introduces a credential
        # ref that does not exist in the keychain, fail before the DB write.
        self._probe_credentials(validated)
        before = await self.get(ref)
        updated = await self._repo.update_config(ref, validated, description)
        await self._audit.record(
            AuditEventType.RESOURCE_UPDATED.value,
            ref=ref,
            actor=actor,
            details={
                "before": _audit_safe_config(before.config),
                "after": _audit_safe_config(validated),
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
            # Hook abort propagates as the caller's exception. If the hook
            # returns an Awaitable (async cleanup), we await it so on-disk
            # teardown completes BEFORE the row is removed — otherwise a
            # follow-up read inside the hook hits ResourceNotFound and the
            # cleanup is silently dropped.
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
                    "config": _audit_safe_config(snapshot.config),
                    "enabled": snapshot.enabled,
                }
            },
        )

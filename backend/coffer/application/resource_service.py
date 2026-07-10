"""Kind-agnostic Resource CRUD service.

The service is constructed with a dict of registered kinds; it never
imports any kind-specific module. Each mutation is audited via
AuditService. `delete` calls the kind's optional `on_delete` hook
BEFORE persistence; a hook that raises aborts the deletion.
"""

from __future__ import annotations

import builtins
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
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
from coffer.domain.scope import ScopeValidationError, validate_scope

_logger = logging.getLogger(__name__)


class _CredentialStorePort(Protocol):
    """Minimal kind-agnostic port for register-time credential probing and
    delete-time release.

    Mirrors :class:`coffer.application.mcp.ports.CredentialStorePort` but
    defined locally so the kind-agnostic resource service does not import
    the mcp-specific port module (importlinter Contract 6).
    """

    def get(self, ref: str) -> str | None: ...

    def exists(self, ref: str) -> bool: ...

    def delete(self, ref: str) -> None: ...


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
    """Return ``{key: credential_ref}`` for ``config`` using the kind's extractor.

    Kinds without a ``credential_ref_extractor`` declare no credentials and are
    not probed.
    """
    if kind_def.credential_ref_extractor is None:
        return {}
    return kind_def.credential_ref_extractor(config)


@dataclass(frozen=True)
class ReleasedCredential:
    """Delete-listener notice for a credential released with its last citer.

    Duck-types ``ResourceRef`` (``.kind``/``.name``) for the listeners'
    benefit; a real ``ResourceRef`` cannot carry it because credential refs
    contain slashes, which the resource name pattern rightly rejects.
    """

    name: str
    kind: str = field(default="credential", init=False)

    def __str__(self) -> str:
        return f"{self.kind}:{self.name}"


class ResourceService:
    def __init__(
        self,
        kinds: dict[str, Kind],
        repo: ResourceRepo,
        audit: AuditService,
        credentials: _CredentialStorePort | None = None,
    ) -> None:
        self._kinds = kinds
        self._repo = repo
        self._audit = audit
        self._credentials = credentials
        # Cross-cutting observers of completed deletions (e.g. the sync
        # tombstone ledger, spec 010) — kind-agnostic, registered by the
        # composition root, called AFTER the row is gone with the acting
        # surface, so sync-applied deletions can be told apart from the user's.
        self._delete_listeners: list[Callable[[ResourceRef | ReleasedCredential, str], Any]] = []
        self._change_listeners: list[Callable[[], Any]] = []

    def add_delete_listener(
        self, listener: Callable[[ResourceRef | ReleasedCredential, str], Any]
    ) -> None:
        """Register a callback (sync or async) invoked after every deletion."""
        self._delete_listeners.append(listener)

    def add_change_listener(self, listener: Callable[[], Any]) -> None:
        """Register a fire-and-forget callback invoked after every mutation
        (register / update / enable / delete) — e.g. the auto-sync debouncer."""
        self._change_listeners.append(listener)

    def _notify_change(self) -> None:
        for listener in self._change_listeners:
            try:
                listener()
            except Exception:
                _logger.exception("resource.change_listener_failed")

    def _probe_credentials(self, kind_def: Kind, config: dict[str, Any]) -> None:
        """Raise CredentialMissing if any cited credential_ref is absent from the credential store.

        Called BEFORE persisting a Resource so a missing credential never
        leaves a partial row in the resources table. Skipped if no credential
        store is wired (back-compat for tests that don't need credential checks).
        """
        if self._credentials is None:
            return
        for _key, ref in _extract_credential_refs(kind_def, config).items():
            if self._credentials.get(ref) is None:
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
        # Kind-supplied semantic validation beyond shape, at REGISTRATION only
        # (e.g. a channel's workspace directories must exist on disk). Kept off
        # update_config so editing an unrelated field never re-probes the
        # filesystem and rejects the edit because a dir was since removed.
        if kind_def.validate_config is not None:
            try:
                kind_def.validate_config(validated)
            except ValueError as e:
                raise ConfigValidationError(str(e)) from e
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
        self._notify_change()
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

    async def find_credential_citations(self, credential_ref: str) -> builtins.list[ResourceRef]:
        """Return the refs of every resource whose config cites ``credential_ref``.

        A credential lives in the encrypted store and is referenced only by its
        ref from resource config (a channel's bot token, an mcp_server's auth
        header, a model's API key). Deleting the credential out from under a
        live resource silently breaks it, so the credential-delete route calls
        this first and refuses (409) when the list is non-empty. Each kind that
        stores secrets supplies a ``credential_ref_extractor``; kinds without
        one cite nothing and are skipped.

        (The return type is spelled ``builtins.list`` because this class also
        defines a ``list`` method, which shadows the builtin in annotations
        appearing after it in the class body.)
        """
        citing: builtins.list[ResourceRef] = []
        for resource in await self._repo.list():
            kind_def = self._kinds.get(resource.kind)
            if kind_def is None:
                continue
            refs = _extract_credential_refs(kind_def, resource.config).values()
            if credential_ref in refs:
                citing.append(resource.ref)
        return citing

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
        # ref that does not exist in the credential store, fail before the DB write.
        self._probe_credentials(kind_def, validated)
        before = await self.get(ref)
        # Per-kind cross-version hook (e.g. ``knowledge_base``/``memory``
        # force a re-index/re-embed when chunk or embedding config changed).
        # May raise ``ConfigValidationError`` to reject the update.
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
        self._notify_change()
        return updated

    async def set_enabled(self, ref: ResourceRef, enabled: bool, actor: str) -> Resource:
        before = await self.get(ref)
        if before.enabled == enabled:
            return before  # idempotent — no audit
        updated = await self._repo.set_enabled(ref, enabled)
        event = AuditEventType.RESOURCE_ENABLED if enabled else AuditEventType.RESOURCE_DISABLED
        await self._audit.record(event.value, ref=ref, actor=actor)
        self._notify_change()
        return updated

    async def update_scope(
        self,
        ref: ResourceRef,
        scope: dict[str, Any] | None,
        *,
        actor: str,
    ) -> Resource:
        """Set (or clear) a resource's machine x agent activation scope (ADR-045).

        Framework-level: unlike ``update_config``/``delete``, this is NOT gated
        on ``allow_lifecycle_kind`` — scope is orthogonal to a kind's creation
        invariants, so it applies uniformly to lifecycle kinds (skill, agent,
        channel) too. ``scope`` is validated against the kind's declared
        ``scope_axes`` (empty means the kind does not support scope at all).
        """
        kind_def = self._require_kind(ref.kind)
        try:
            validate_scope(scope, axes=kind_def.scope_axes)
        except ScopeValidationError as e:
            raise ConfigValidationError(str(e)) from e
        # Confirms existence up front (raises ResourceNotFound) — mirrors
        # update_config's before-read.
        await self.get(ref)
        updated = await self._repo.update_scope(ref, scope)
        if updated is None:
            raise ResourceNotFound(ref.kind, ref.name)
        await self._audit.record(
            AuditEventType.RESOURCE_SCOPE_UPDATED.value,
            ref=ref,
            actor=actor,
            # Scope carries only machine ids / agent names — no secrets — so it
            # is audited verbatim (no redactor needed, unlike config).
            details={"scope": scope},
        )
        self._notify_change()
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
        released = await self._release_orphaned_credentials(kind_def, snapshot.config, actor)
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
        # Released credentials notify like deletions of their own pseudo-kind
        # so the sync ledger tombstones them and other machines drop their
        # copies too (an orphan row would re-export on every future sync).
        notifications: list[ResourceRef | ReleasedCredential] = [ref]
        notifications += [ReleasedCredential(r) for r in released]
        for listener in self._delete_listeners:
            # A listener failure must not turn an already-completed deletion
            # into a caller-facing error.
            for notice in notifications:
                try:
                    result = listener(notice, actor)
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    _logger.exception("resource.delete_listener_failed", extra={"ref": str(notice)})
        self._notify_change()

    async def _release_orphaned_credentials(
        self, kind_def: Kind, config: dict[str, Any], actor: str
    ) -> builtins.list[str]:
        """Drop the deleted resource's credentials that nothing cites anymore.

        Runs after the row is removed, so the deleted resource no longer counts
        as a citation of its own refs. A failure must not turn the completed
        deletion into a caller-facing error — the credential then merely
        lingers, which was the status quo.
        """
        if self._credentials is None:
            return []
        released: builtins.list[str] = []
        for cred_ref in dict.fromkeys(_extract_credential_refs(kind_def, config).values()):
            try:
                if not self._credentials.exists(cred_ref):
                    continue
                if await self.find_credential_citations(cred_ref):
                    continue
                self._credentials.delete(cred_ref)
                await self._audit.record(
                    AuditEventType.CREDENTIAL_DELETED.value,
                    actor=actor,
                    details={"ref": cred_ref},
                )
                released.append(cred_ref)
            except Exception:
                _logger.exception("resource.credential_release_failed", extra={"ref": cred_ref})
        return released

"""Kind-agnostic Resource CRUD service.

The service is constructed with a dict of registered kinds; it never
imports any kind-specific module. Each mutation is audited via
AuditService. `delete` calls the kind's optional `on_delete` hook
BEFORE persistence; a hook that raises aborts the deletion.

Two mutation paths delegate to sibling ops modules to keep this file under
the 400-LOC ceiling (mirroring `skill/service.py` + its `*_ops.py` satellites):
`update_scope`'s body lives in `resource_scope_ops`, and `delete`'s
credential-release step lives in `resource_delete_ops`.
"""

from __future__ import annotations

import asyncio
import builtins
import inspect
import logging
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
    RenameNotSupported,
    ResourceNotFound,
    UnknownKind,
)
from coffer.domain.resource import Kind, Resource, ResourceRef
from coffer.domain.scope import Scope

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
    config verbatim. See the resource-framework-upfront ADR / CODE-006.
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

    async def _probe_credentials(self, kind_def: Kind, config: dict[str, Any]) -> None:
        """Raise CredentialMissing if any cited credential_ref is absent from the credential store.

        Called BEFORE persisting a Resource so a missing credential never
        leaves a partial row in the resources table. Skipped if no credential
        store is wired (back-compat for tests that don't need credential checks).

        The store's ``get`` is a blocking SQLite read, so it runs in a worker
        thread: on the loop it would stall every other request for as long as
        the read (and any lock it waits on) takes.
        """
        if self._credentials is None:
            return
        for _key, ref in _extract_credential_refs(kind_def, config).items():
            if await asyncio.to_thread(self._credentials.get, ref) is None:
                raise CredentialMissing(ref)

    def _require_kind(self, kind: str) -> Kind:
        if kind not in self._kinds:
            raise UnknownKind(kind)
        return self._kinds[kind]

    def converges(self, kind: str) -> bool:
        """Whether this kind's rows travel to the sync remote (spec vault-sync).

        Public for the same reason ``supports_scope`` is: the sync layer has to
        ask, and the answer belongs to the kind.

        An unregistered kind answers **True**, which is the conservative answer
        and not the obvious one. This flag exists only to withhold, so a kind
        nobody has declared anything about must keep whatever behaviour it had:
        an unknown kind arriving in a document still reaches
        ``register`` and is still refused there by name (``UnknownKind``).
        Answering False would have turned that named refusal into a silent skip
        — a document quietly doing nothing is exactly what a converge round
        must not produce.
        """
        kind_def = self._kinds.get(kind)
        return kind_def.converges if kind_def is not None else True

    def supports_scope(self, kind: str) -> bool:
        """Whether the kind carries a per-agent activation scope (ADR per-agent-resource-scope).

        Public accessor (unlike ``_require_kind``) so the REST GET
        .../scope route can tell a client whether scope may be set at all,
        without reaching into the private kinds registry.
        """
        return self._require_kind(kind).supports_scope

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
        await self._probe_credentials(kind_def, validated)
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
                # A freshly registered resource is unscoped (ADR per-agent-resource-scope) —
                # active for every agent until the user narrows it — UNLESS the
                # kind supplies a starting scope. Only `provider` does: "every
                # agent" would widen a new connection past the wire default its
                # projection targets used to come from.
                scope=(
                    kind_def.default_scope(validated)
                    if kind_def.default_scope is not None
                    else None
                ),
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
        await self._probe_credentials(kind_def, validated)
        before = await self.get(ref)
        # Per-kind pre-write hook. Only ``channel`` supplies one: it
        # re-validates ``default_agent`` against the live agent registry and
        # the channel's own scope. May raise ``ConfigValidationError`` to
        # reject the update.
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
        kind_def = self._require_kind(ref.kind)
        before = await self.get(ref)
        if before.enabled == enabled:
            return before  # idempotent — no audit, no hook
        updated = await self._repo.set_enabled(ref, enabled)
        event = AuditEventType.RESOURCE_ENABLED if enabled else AuditEventType.RESOURCE_DISABLED
        await self._audit.record(event.value, ref=ref, actor=actor)
        # Kind-level reconciliation, exactly as ``update_scope`` fires
        # ``on_scope_changed``: AFTER persistence + audit, so a hook re-reading
        # the resource sees the flag that triggered it. Fired only on a real
        # transition (the idempotent early return above skips it).
        if kind_def.on_enabled_changed is not None:
            hook_result = kind_def.on_enabled_changed(ref)
            if inspect.isawaitable(hook_result):
                await hook_result
        return updated

    async def update_scope(
        self,
        ref: ResourceRef,
        scope: Scope | None,
        *,
        actor: str,
    ) -> Resource:
        """Set (or clear) a resource's per-agent activation scope (ADR per-agent-resource-scope).

        Delegates to ``resource_scope_ops`` to keep this module under the
        file-size limit; see that module for the full behavior.
        """
        from coffer.application.resource_scope_ops import update_scope as _update_scope

        return await _update_scope(self, ref, scope, actor=actor)

    async def rename(
        self,
        ref: ResourceRef,
        new_name: str,
        actor: str,
        *,
        allow_lifecycle_kind: bool = False,
    ) -> Resource:
        """Move a resource to ``new_name``.

        Its own operation rather than an ``update_config`` on the name because
        a name is not config — but all it does is move the row. The audit trail
        needs no repointing: rows carry the resource's stable id, so history
        follows it while each row keeps saying what the resource was called
        when that event happened. The rename is recorded as its own event.

        The KIND decides whether the KIND-AGNOSTIC surface may do it (FR-010).
        A name is a label, but it is also this framework's address, so a kind
        whose name is written out somewhere this move cannot reach — into
        another tool's config, into a folder on disk — would be left with that
        reference pointing at nothing. Those kinds declare no rename here and
        rename through their own service, which passes
        ``allow_lifecycle_kind`` and then repairs what it knows about. Exactly
        the seam ``update_config`` already draws for the same reason.
        """
        kind_def = self._require_kind(ref.kind)
        if not kind_def.supports_rename and not allow_lifecycle_kind:
            raise RenameNotSupported(ref.kind)
        # Same CODE-030 name check ``register`` applies, BEFORE any DB write.
        if kind_def.validate_name is not None:
            try:
                kind_def.validate_name(new_name)
            except ValueError as e:
                raise ConfigValidationError(str(e)) from e
        before = await self.get(ref)  # 404 for an absent resource, before anything moves
        if before.name == new_name:
            # The name it already has renames nothing and records nothing — a
            # dialog submitted with that field untouched has not renamed.
            return before
        renamed = await self._repo.rename(ref, new_name)
        await self._audit.record(
            AuditEventType.RESOURCE_RENAMED.value,
            ref=ResourceRef(ref.kind, new_name),
            actor=actor,
            details={"from": ref.name, "to": new_name},
        )
        return renamed

    async def delete(self, ref: ResourceRef, actor: str) -> None:
        # Credential release (on successful delete) delegates to
        # resource_delete_ops to keep this module under the file-size limit.
        from coffer.application.resource_delete_ops import release_orphaned_credentials

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
        await release_orphaned_credentials(self, kind_def, snapshot.config, actor)
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

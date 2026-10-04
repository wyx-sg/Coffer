"""Kind-agnostic Resource CRUD service.

Every resource is addressed by its **uid** — opaque, immutable, and the same
value on every machine that holds it (ADR identity-is-the-uid-inside-the-file).
``get_by_name`` is the one exception and exists for one job: resolving a label a
human supplied, at the surface they supplied it to. Nothing inside the daemon
should reach for it.

The service is constructed with a dict of registered kinds; it never
imports any kind-specific module. Each mutation is audited via
AuditService. `delete` calls the kind's optional `on_delete` hook
BEFORE persistence; a hook that raises aborts the deletion.

Sibling ops modules keep this file under the 400-LOC ceiling (mirroring
`skill/service.py` + its `*_ops.py` satellites): `update_scope`'s body lives in
`resource_scope_ops`, `set_enabled`'s in `resource_enable_ops`, `rename`'s in
`resource_rename_ops`, `set_title`'s in `resource_title_ops`, `delete`'s
secret-release step in `resource_delete_ops`, the registration secret probe in
`resource_secret_ops`, and every question about what
a kind *declares* — where it is stored, what redacts, what cites a secret, what
it will accept as a name — in `resource_kind_ops`.
"""

from __future__ import annotations

import builtins
import inspect
import logging
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import ValidationError

from coffer.application import resource_kind_ops, resource_secret_ops
from coffer.application.audit_service import AuditService
from coffer.application.repos import ResourceRepo
from coffer.application.resource_actor import acting_as
from coffer.application.resource_bindings import BindingSettlerPort, settle_bindings
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    ConfigValidationError,
    GenericCreateNotAllowed,
    ResourceNotFound,
    UnknownKind,
)
from coffer.domain.resource import Kind, Resource
from coffer.domain.scope import Scope
from coffer.domain.vault.layout import StorageClass

_logger = logging.getLogger(__name__)


class _SecretStorePort(Protocol):
    """Minimal kind-agnostic port for register-time secret probing and
    delete-time release.

    Mirrors :class:`coffer.application.mcp.ports.SecretStorePort` but
    defined locally so the kind-agnostic resource service does not import
    the mcp-specific port module (importlinter Contract 6).
    """

    def get(self, ref: str) -> str | None: ...

    def exists(self, ref: str) -> bool: ...

    def delete(self, ref: str) -> None: ...


class ResourceService:
    def __init__(
        self,
        kinds: dict[str, Kind],
        repo: ResourceRepo,
        audit: AuditService,
        secrets: _SecretStorePort | None = None,
        bindings: BindingSettlerPort | None = None,
    ) -> None:
        self._kinds = kinds
        self._repo = repo
        self._audit = audit
        self._secrets = secrets
        self._bindings = bindings

    def set_binding_settler(self, settler: BindingSettlerPort | None) -> None:
        """Install the post-register seam, once every kind has declared where
        its secrets go (spec secret "Approve a secret's binding when its
        destination is registered")."""
        self._bindings = settler

    async def _probe_secrets(self, kind_def: Kind, config: dict[str, Any]) -> None:
        """Raise SecretMissing if a cited secret_ref has no value (resource_secret_ops)."""
        if self._secrets is not None:
            await resource_secret_ops.probe_secrets(self._secrets, kind_def, config)

    def _require_kind(self, kind: str) -> Kind:
        if kind not in self._kinds:
            raise UnknownKind(kind)
        return self._kinds[kind]

    def storage_of(self, kind: str, config: Mapping[str, Any]) -> StorageClass:
        """The storage class a resource of ``kind`` with ``config`` is filed in
        (ADR storage-is-five-classes-by-nature)."""
        return resource_kind_ops.storage_of(self._kinds, kind, config)

    def supports_scope(self, kind: str) -> bool:
        """Whether the kind carries a per-agent activation scope (ADR per-agent-resource-scope).

        Public accessor (unlike ``_require_kind``) so the REST GET
        .../scope route can tell a client whether scope may be set at all,
        without reaching into the private kinds registry.
        """
        return self._require_kind(kind).supports_scope

    def toggleable(self, kind: str) -> bool:
        """Whether the kind's resources carry an enabled switch at all."""
        return self._require_kind(kind).toggleable

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
        title: str | None = None,
    ) -> Resource:
        """Create a resource and mint its identity: a fresh random uid, because
        minting one from anything a user can change is what this whole design
        removed. A resource that arrives from another machine arrives as a file
        carrying its uid, never through here."""
        kind_def = self._require_kind(kind)
        # spec resource-framework "Keep creation a per-kind seam": a kind that
        # owns creation invariants beyond config (skill master folder, agent
        # on-disk detection) sets ``generic_create_allowed=False``, so the
        # generic POST path cannot create a row with no backing artifact; the
        # kind's dedicated service opts in with ``allow_lifecycle_kind``.
        if not kind_def.generic_create_allowed and not allow_lifecycle_kind:
            raise GenericCreateNotAllowed(kind)
        resource_kind_ops.check_name(kind_def, name)
        title = resource_kind_ops.checked_title(kind_def, title)
        validated = self._validate_config(kind_def, config)
        resource_kind_ops.check_derived_name(kind_def, name, validated)
        # Kind-supplied semantic validation beyond shape, at REGISTRATION only
        # (e.g. a channel's workspace directories must exist on disk), so
        # editing an unrelated field never re-probes the filesystem. Awaited
        # when it returns an Awaitable: `channel` checks that its
        # `default_agent` uid names a registered agent, which only the resource
        # table can answer — and an unawaited coroutine is a validator that
        # silently passes everything.
        if kind_def.validate_config is not None:
            try:
                check = kind_def.validate_config(validated)
                if inspect.isawaitable(check):
                    await check
            except ValueError as e:
                raise ConfigValidationError(str(e)) from e
        # Probe before any write — a missing secret must not leave a
        # half-created resource file behind. Spec mcp-gateway "Manage MCP
        # servers as resources" requires registration to fail naming the missing ref.
        await self._probe_secrets(kind_def, validated)
        now = datetime.now(tz=UTC)
        with acting_as(actor):
            created = await self._repo.create(
                Resource(
                    # The identity, minted here so it is decided before anything
                    # is written; the store files it inside the resource's file.
                    uid=uuid.uuid4().hex,
                    kind=kind,
                    name=name,
                    description=description,
                    config=validated,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                    title=title,
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
            resource=created,
            actor=actor,
            details={"config": resource_kind_ops.audit_safe_config(kind_def, validated)},
        )
        await settle_bindings(self._bindings, created, actor)
        return created

    async def list(
        self,
        kind: str | None = None,
        enabled: bool | None = None,
    ) -> list[Resource]:
        return await self._repo.list(kind=kind, enabled=enabled)

    async def get(self, uid: str) -> Resource:
        r = await self._repo.find(uid)
        if r is None:
            raise ResourceNotFound(uid)
        return r

    async def get_by_name(self, kind: str, name: str) -> Resource:
        """Resolve a LABEL a human supplied. The CLI's front door, and nothing
        inside the daemon addresses a resource this way."""
        self._require_kind(kind)
        r = await self._repo.find_by_name(kind, name)
        if r is None:
            raise ResourceNotFound.named(kind, name)
        return r

    async def find_by_name(self, kind: str, name: str) -> Resource | None:
        return await self._repo.find_by_name(kind, name)

    async def find_secret_citations(self, secret_ref: str) -> builtins.list[Resource]:
        """Every resource whose config cites ``secret_ref``.

        (Spelled ``builtins.list`` because this class also defines a ``list``
        method, which shadows the builtin in annotations appearing after it.)

        Delegates to ``resource_delete_ops``, which is the other half of the
        same question: this one answers "may this secret be deleted?" for
        the secret route, and that one answers "is anything still citing
        it?" after a resource goes away.
        """
        from coffer.application.resource_delete_ops import citations_of

        return await citations_of(self, secret_ref)

    async def cited_secret_refs(self) -> dict[str, builtins.list[Resource]]:
        """Every secret ref cited by any resource, mapped to its citers."""
        from coffer.application.resource_delete_ops import all_citations

        return await all_citations(self)

    async def update_config(
        self,
        uid: str,
        new_config: dict[str, Any],
        actor: str,
        description: str | None = None,
        *,
        allow_lifecycle_kind: bool = False,
    ) -> Resource:
        before = await self.get(uid)
        kind_def = self._require_kind(before.kind)
        # The per-kind creation seam applies to updates too: a generic PATCH
        # rewriting a lifecycle kind's config would desync the row from the on-disk
        # artifact its owning service maintains.
        if not kind_def.generic_create_allowed and not allow_lifecycle_kind:
            raise GenericCreateNotAllowed(before.kind)
        validated = self._validate_config(kind_def, new_config)
        # Same register-time invariant: if the update introduces a secret
        # ref that does not exist in the secret store, fail before the write.
        await self._probe_secrets(kind_def, validated)
        # Per-kind pre-write hook. Only ``channel`` supplies one: it
        # re-validates ``default_agent`` against the live agent registry and
        # the channel's own scope. May raise ``ConfigValidationError`` to
        # reject the update.
        if kind_def.on_update_config is not None:
            hook_result = kind_def.on_update_config(before, validated)
            if inspect.isawaitable(hook_result):
                await hook_result
        with acting_as(actor):
            updated = await self._repo.update_config(uid, validated, description)
        await self._audit.record(
            AuditEventType.RESOURCE_UPDATED.value,
            resource=updated,
            actor=actor,
            details={
                "before": resource_kind_ops.audit_safe_config(kind_def, before.config),
                "after": resource_kind_ops.audit_safe_config(kind_def, validated),
            },
        )
        await settle_bindings(self._bindings, updated, actor)
        return updated

    async def set_enabled(self, uid: str, enabled: bool, actor: str) -> Resource:
        """Flip a resource's enabled flag; see ``resource_enable_ops``."""
        from coffer.application.resource_enable_ops import set_enabled as _set_enabled

        return await _set_enabled(self, uid, enabled, actor=actor)

    async def update_scope(
        self,
        uid: str,
        scope: Scope | None,
        *,
        actor: str,
    ) -> Resource:
        """Set (or clear) a resource's per-agent activation scope (ADR per-agent-resource-scope).

        Delegates to ``resource_scope_ops`` to keep this module under the
        file-size limit; see that module for the full behavior.
        """
        from coffer.application.resource_scope_ops import update_scope as _update_scope

        return await _update_scope(self, uid, scope, actor=actor)

    async def rename(self, uid: str, new_name: str, actor: str) -> Resource:
        """Change a resource's LABEL — one column, since cross-resource
        references, the synced document and the audit trail all hold the uid.
        A kind whose name is quoted outside Coffer declares it fixed
        (``Kind.name_fixed``) and is refused with ``NameImmutable``. See
        ``resource_rename_ops`` for the order of operations.
        """
        from coffer.application.resource_rename_ops import rename as _rename

        return await _rename(self, uid, new_name, actor)

    def refuse_fixed_name(self, resource: Resource, new_name: str) -> None:
        """``NameImmutable`` when ``new_name`` would change a fixed name — for a
        caller that must refuse before writing anything else (the update route)."""
        from coffer.application.resource_rename_ops import refuse_fixed_name

        refuse_fixed_name(self._require_kind(resource.kind), resource, new_name)

    async def set_title(self, uid: str, title: str | None, actor: str) -> Resource:
        """Set a resource's display title; ``None`` or blank clears it. Every
        kind, fixed name or not; see ``resource_title_ops``."""
        from coffer.application.resource_title_ops import set_title as _set_title

        return await _set_title(self, uid, title, actor)

    async def delete(self, uid: str, actor: str) -> None:
        # Secret release (on successful delete) delegates to
        # resource_delete_ops to keep this module under the file-size limit.
        from coffer.application.resource_delete_ops import release_orphaned_secrets

        snapshot = await self.get(uid)  # raises ResourceNotFound if missing
        kind_def = self._require_kind(snapshot.kind)
        if kind_def.validate_delete is not None:
            # Pre-write guard: refuses BEFORE on_delete tears anything down,
            # so a refused delete leaves the resource exactly as it was.
            kind_def.validate_delete(snapshot)
        # A file that cannot be removed now (read-only, or an unsettled edit)
        # is refused before the kind's hook tears its on-disk half down.
        await self._repo.ensure_writable(uid)
        if kind_def.on_delete is not None:
            # Await an async on_delete hook so side effects (e.g.
            # evicting live upstream connections, tearing down skill symlinks)
            # COMPLETE before the file is removed. A sync hook still runs
            # synchronously. A hook that raises aborts the deletion (propagates
            # to the caller). Otherwise a follow-up read inside the hook would
            # hit ResourceNotFound and the cleanup would be silently dropped.
            result = kind_def.on_delete(snapshot)
            if inspect.isawaitable(result):
                await result
        with acting_as(actor):
            await self._repo.delete(uid)
        await release_orphaned_secrets(self, kind_def, snapshot.config, actor)
        await self._audit.record(
            AuditEventType.RESOURCE_DELETED.value,
            resource=snapshot,
            actor=actor,
            details={
                "snapshot": {
                    "kind": snapshot.kind,
                    "name": snapshot.name,
                    "config": resource_kind_ops.audit_safe_config(kind_def, snapshot.config),
                    "enabled": snapshot.enabled,
                }
            },
        )

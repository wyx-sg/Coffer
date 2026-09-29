"""Kind-agnostic Resource CRUD service.

Every resource is addressed by its **uid** — opaque, immutable, and the same
value on every machine that holds it (ADR resource-identity-is-an-immutable-uid).
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
credential-release step in `resource_delete_ops`, and every question about what
a kind *declares* — what converges, what redacts, what cites a credential, what
it will accept as a name — in `resource_kind_ops`.
"""

from __future__ import annotations

import asyncio
import builtins
import inspect
import logging
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import ValidationError

from coffer.application import resource_kind_ops
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
from coffer.domain.resource import Kind, Resource
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
        for _key, ref in resource_kind_ops.credential_refs(kind_def, config).items():
            if await asyncio.to_thread(self._credentials.get, ref) is None:
                raise CredentialMissing(ref)

    def _require_kind(self, kind: str) -> Kind:
        if kind not in self._kinds:
            raise UnknownKind(kind)
        return self._kinds[kind]

    def converges(self, kind: str) -> bool:
        """Whether this kind's rows travel to the sync remote (spec vault-sync)."""
        return resource_kind_ops.converges(self._kinds, kind)

    def converges_row(self, kind: str, config: Mapping[str, Any]) -> bool:
        """Whether **this one row** travels to the sync remote (spec vault-sync)."""
        return resource_kind_ops.converges_row(self._kinds, kind, config)

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
        uid: str | None = None,
        title: str | None = None,
    ) -> Resource:
        """Create a resource and mint its identity.

        ``uid`` is supplied by exactly one caller — the sync applier, putting a
        resource this vault has not seen before at the identity the other
        machine already gave it. Every other path leaves it ``None`` and gets a
        fresh random one, because minting a uid from anything a user can change
        is what this whole design removed.
        """
        kind_def = self._require_kind(kind)
        # spec resource-framework "Keep creation a per-kind seam": a kind that
        # owns creation invariants beyond config (skill master folder, agent
        # on-disk detection) sets ``generic_create_allowed=False``, so the
        # generic POST path cannot create a row with no backing artifact; the
        # kind's dedicated service opts in with ``allow_lifecycle_kind``.
        if not kind_def.generic_create_allowed and not allow_lifecycle_kind:
            raise GenericCreateNotAllowed(kind)
        resource_kind_ops.check_name(kind_def, name)
        if uid is None:
            # A resource created HERE, not one arriving with the identity another
            # machine gave it: only a new name meets a kind's rules for new names.
            resource_kind_ops.check_new_name(kind_def, name)
        title = resource_kind_ops.checked_title(title)
        validated = self._validate_config(kind_def, config)
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
        # Probe before any DB write — a missing credential must not leave a
        # half-created resource row behind. Spec mcp-gateway "Manage MCP
        # servers as resources" requires registration to fail naming the missing ref.
        await self._probe_credentials(kind_def, validated)
        now = datetime.now(tz=UTC)
        created = await self._repo.create(
            Resource(
                # 0 is the surrogate key's placeholder — the repo assigns it.
                # The uid is NOT a placeholder: it is the identity, minted here
                # so it is decided before anything is written.
                id=0,
                uid=uid or uuid.uuid4().hex,
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

    async def find_credential_citations(self, credential_ref: str) -> builtins.list[Resource]:
        """Every resource whose config cites ``credential_ref``.

        (Spelled ``builtins.list`` because this class also defines a ``list``
        method, which shadows the builtin in annotations appearing after it.)

        Delegates to ``resource_delete_ops``, which is the other half of the
        same question: this one answers "may this credential be deleted?" for
        the credential route, and that one answers "is anything still citing
        it?" after a resource goes away.
        """
        from coffer.application.resource_delete_ops import citations_of

        return await citations_of(self, credential_ref)

    async def cited_credential_refs(self) -> dict[str, builtins.list[Resource]]:
        """Every credential ref cited by any resource, mapped to its citers."""
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
        # Same register-time invariant: if the update introduces a credential
        # ref that does not exist in the credential store, fail before the DB write.
        await self._probe_credentials(kind_def, validated)
        # Per-kind pre-write hook. Only ``channel`` supplies one: it
        # re-validates ``default_agent`` against the live agent registry and
        # the channel's own scope. May raise ``ConfigValidationError`` to
        # reject the update.
        if kind_def.on_update_config is not None:
            hook_result = kind_def.on_update_config(before, validated)
            if inspect.isawaitable(hook_result):
                await hook_result
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
        # Credential release (on successful delete) delegates to
        # resource_delete_ops to keep this module under the file-size limit.
        from coffer.application.resource_delete_ops import release_orphaned_credentials

        snapshot = await self.get(uid)  # raises ResourceNotFound if missing
        kind_def = self._require_kind(snapshot.kind)
        if kind_def.validate_delete is not None:
            # Pre-write guard: refuses BEFORE on_delete tears anything down,
            # so a refused delete leaves the resource exactly as it was.
            kind_def.validate_delete(snapshot)
        if kind_def.on_delete is not None:
            # Await an async on_delete hook so side effects (e.g.
            # evicting live upstream connections, tearing down skill symlinks)
            # COMPLETE before the row is removed. A sync hook still runs
            # synchronously. A hook that raises aborts the deletion (propagates
            # to the caller). Otherwise a follow-up read inside the hook would
            # hit ResourceNotFound and the cleanup would be silently dropped.
            result = kind_def.on_delete(snapshot)
            if inspect.isawaitable(result):
                await result
        await self._repo.delete(uid)
        await release_orphaned_credentials(self, kind_def, snapshot.config, actor)
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

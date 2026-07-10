"""Core Resource domain entities."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]+$")
_NAME_MAX_LEN = 64


@dataclass(frozen=True)
class ResourceRef:
    """External identifier for any Resource: `<kind>:<name>`."""

    kind: str
    name: str

    def __post_init__(self) -> None:
        if not self.kind or ":" in self.kind:
            raise ValueError(f"invalid kind: {self.kind!r}")
        if not self.name:
            raise ValueError(f"invalid name: {self.name!r}")
        if len(self.name) > _NAME_MAX_LEN:
            raise ValueError(
                f"name too long ({len(self.name)} chars, max {_NAME_MAX_LEN}): {self.name!r}"
            )
        if not _NAME_PATTERN.match(self.name):
            raise ValueError(f"invalid name {self.name!r}: must match ^[a-zA-Z0-9_.-]+$")

    def __str__(self) -> str:
        return f"{self.kind}:{self.name}"

    @classmethod
    def parse(cls, s: str) -> ResourceRef:
        parts = s.split(":")
        if len(parts) != 2:
            raise ValueError(f"expected '<kind>:<name>', got {s!r}")
        kind, name = parts
        if not kind or not name:
            raise ValueError(f"empty kind or name in {s!r}")
        return cls(kind=kind, name=name)


@dataclass
class Resource:
    """A user-managed entity inside Coffer.

    Resources share the kind-agnostic shape; kind-specific behaviour
    lives in services keyed off the `kind` field.
    """

    id: int
    kind: str
    name: str
    description: str | None
    config: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime
    # Framework-level machine x agent activation scope (ADR-045). None means
    # unscoped (visible everywhere) — the pre-scope default, so every existing
    # constructor keeps working unchanged. Interpreted via coffer.domain.scope;
    # only kinds whose Kind.scope_axes is non-empty may set it (validate_scope).
    scope: dict[str, Any] | None = None

    @property
    def ref(self) -> ResourceRef:
        return ResourceRef(self.kind, self.name)


@dataclass(frozen=True)
class Kind:
    """Pure descriptor of a resource kind.

    Held by ResourceService; lookup-only. Surface-layer bindings (routers,
    CLI groups) live in KindModule (composition root) not here.
    """

    name: str
    display_name: str
    config_schema: type[BaseModel]
    # The hook may return ``None`` (purely synchronous) or an ``Awaitable``;
    # the kind-agnostic ResourceService awaits the result when present so
    # cleanup completes BEFORE the row is removed (a fire-and-forget task
    # would race the delete and find a ResourceNotFound on follow-up reads).
    on_delete: Callable[[ResourceRef], Awaitable[None] | None] | None = None
    # Optional kind-specific name validator, called at register time BEFORE
    # persistence. Raises to reject the name. Used by `mcp_server` to reserve
    # the `__` tool/prompt namespace separator (CODE-030).
    validate_name: Callable[[str], None] | None = None
    # Whether the kind-agnostic POST /api/v1/resources endpoint may create this
    # kind. Kinds that own creation invariants beyond config validation — a
    # skill's master folder under ~/.coffer/skills/, an agent's on-disk
    # detection — set this False so the generic path cannot create a row with
    # no backing artifact. Their dedicated services still create rows by
    # passing ``allow_lifecycle_kind=True`` to ResourceService.register
    # (CODE-REG, symmetric with the on_delete cleanup hook).
    generic_create_allowed: bool = True
    # Optional kind-supplied audit redactor: given a validated config dict,
    # return an audit-safe copy with secret-bearing fields stripped. Keeps the
    # kind-agnostic ResourceService from hardcoding any one kind's config shape
    # (e.g. mcp_server's ``transport.env``/``headers``) — ADR-001 / CODE-006.
    audit_redactor: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    # Optional kind-supplied credential-ref extractor: given a validated config
    # dict, return ``{logical_key: keychain_ref}``. ResourceService probes each
    # ref at register/update time so a missing credential fails before any DB
    # write — without the core knowing where a kind stores its refs.
    credential_ref_extractor: Callable[[dict[str, Any]], dict[str, str]] | None = None
    # Optional semantic config validation beyond ``config_schema`` shape,
    # applied at REGISTRATION only (already shape-validated). Given the validated
    # config dict; raises ``ValueError`` to reject the write (e.g. a channel's
    # workspace directories must exist on disk). Deliberately not run on
    # update_config, so editing an unrelated field never re-probes the filesystem.
    validate_config: Callable[[dict[str, Any]], None] | None = None
    # Optional pre-write hook for ``ResourceService.update_config``.
    # Receives ``(ref, before_config, after_config)`` (both already shape-validated
    # against ``config_schema``); may raise ``ConfigValidationError`` to reject the
    # update, or trigger side effects — ``knowledge_base``/``memory`` force a
    # re-index/re-embed when chunk or embedding config changed (FR-014). Sync or
    # async; the service awaits an Awaitable.
    on_update_config: (
        Callable[
            [ResourceRef, dict[str, Any], dict[str, Any]],
            Awaitable[None] | None,
        ]
        | None
    ) = None
    # Machine x agent activation-scope axes this kind supports (ADR-045), used
    # by ResourceService.update_scope to validate a scope payload via
    # coffer.domain.scope.validate_scope. Empty (the default) means the kind
    # does not support scope at all — any non-null update_scope call for it is
    # rejected. ``("machine",)`` allows only per-machine on/off; ``("machine",
    # "agent")`` additionally allows narrowing to specific agents per machine.
    scope_axes: tuple[str, ...] = ()
    # Optional kind-level shape constraint on a scope payload, layered on TOP
    # of the axis-generic ``validate_scope`` (ADR-045 review Fix 1). Given the
    # already axis-validated scope dict (or ``None``); raises ``ValueError`` to
    # reject a shape the generic axes check can't express. ``scope_axes`` alone
    # says WHICH axes and value shapes are legal, not how many entries a kind
    # can tolerate — e.g. a channel's platform identity (a polled bot, a
    # webhook endpoint) tolerates only ONE machine consumer (ADR-043); two
    # exact-ULID entries, or the ``"*"`` wildcard key, would each start its
    # adapter on more than one machine at once and refight the platform. Kinds
    # that are legitimately multi-machine despite ``("machine",)`` being their
    # only axis (e.g. agent) leave this ``None`` (the default): no extra shape
    # constraint beyond the generic axis check.
    validate_scope_shape: Callable[[dict[str, Any] | None], None] | None = None
    # Optional post-write hook for ``ResourceService.update_scope`` (ADR-045,
    # Task 11 Fix 2). Receives the ref whose scope just changed; invoked AFTER
    # persistence + audit (unlike ``on_update_config``, which runs BEFORE —
    # scope reconciliation needs to read the already-persisted scope), so it
    # cannot reject the edit, only react to it. Sync or async; the service
    # awaits an Awaitable. Kind-level side effect that keeps delivery/reclaim
    # in step with a LOCAL scope edit — the sync import path already re-runs
    # this reconciliation via its own post-import hooks; this is the front-door
    # equivalent so a user editing scope in the UI/CLI sees it applied
    # immediately instead of waiting on an unrelated trigger.
    on_scope_changed: (
        Callable[
            [ResourceRef],
            Awaitable[None] | None,
        ]
        | None
    ) = None
    # Optional kind-supplied scope a freshly REGISTERED resource of this kind
    # starts with (ADR-045 amendment, spec 009 runs_on -> scope migration).
    # ``None`` (the default for every other kind) means the pre-scope default:
    # unscoped / active everywhere, unchanged. A kind whose OWN prior
    # kind-specific field defaulted to "off" (e.g. channel's ``runs_on: null``
    # meant "runs nowhere until the user picks a machine") sets this to ``{}``
    # so a newly registered resource keeps that off-by-default safety instead
    # of silently becoming scope=None (active everywhere) now that scope
    # supersedes the old field. Must already satisfy the kind's own
    # ``scope_axes`` — not re-validated at registration (developer-controlled,
    # not user input).
    default_scope: dict[str, Any] | None = None

"""Core Resource domain entities."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from coffer.domain.scope import Scope

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
    # Framework-level activation scope (ADR per-agent-resource-scope): one
    # allow-list of agents. None means unscoped (active for every agent) — the
    # pre-scope default, so every existing constructor keeps working unchanged.
    # Scope is machine-local: it is set on the machine it applies to and does
    # not travel with the vault (spec vault-sync ``## What does not sync``).
    # Interpreted via coffer.domain.scope; only kinds whose Kind.supports_scope
    # is True may set it (validate_scope).
    scope: Scope | None = None

    @property
    def ref(self) -> ResourceRef:
        return ResourceRef(self.kind, self.name)


@dataclass(frozen=True)
class Kind:
    """Pure descriptor of a resource kind.

    Held by ResourceService; lookup-only. Each kind's ``make_<kind>_kind()``
    factory in ``application/<kind>/kind.py`` returns one of these. Surface
    artefacts (HTTP routers, Typer groups) are NOT carried here: the
    composition root registers them itself through its per-kind wiring
    modules (``surfaces/http/<kind>_wiring.py`` and ``surfaces/cli/main.py``),
    so the domain layer never references a surface.
    """

    name: str
    display_name: str
    config_schema: type[BaseModel]
    # Whether the kind-agnostic POST /api/v1/resources endpoint may create this
    # kind. Kinds that own creation invariants beyond config validation — a
    # skill's master folder under ~/.coffer/skills/, an agent's on-disk
    # detection — set this False so the generic path cannot create a row with
    # no backing artifact. Their dedicated services still create rows by
    # passing ``allow_lifecycle_kind=True`` to ResourceService.register
    # (CODE-REG, symmetric with the on_delete cleanup hook).
    generic_create_allowed: bool = True
    # Whether this kind supports the framework-level per-agent activation
    # scope (ADR per-agent-resource-scope). False (the default) means the kind has no scope at all:
    # ResourceService.update_scope rejects any non-null payload for it (422).
    # `mcp_server`, `skill`, `knowledge`, `memory`, `channel` and `provider`
    # set this True; `agent` deliberately does not — it IS the agent, so there
    # is nothing for a per-agent scope to narrow.
    supports_scope: bool = False
    # Whether this kind's rows converge with the sync remote (spec vault-sync).
    # True for everything the user authored — the rows a second machine is
    # supposed to receive. False for a kind whose rows are DERIVED from what is
    # installed on one machine: publishing those produces, at the other end, a
    # row naming something that machine does not have, with nothing behind it,
    # which the next local pass would recompute away anyway. `memory` is the
    # only kind that sets it False today (spec memory FR-023). Declared here
    # rather than listed in the exporter so the sync layer keeps one rule
    # instead of a table of exceptions — the shape the retired machine-local
    # kind list had.
    converges: bool = True

    # --- Pre-write validators: run BEFORE persistence; raising rejects the write ---

    # Optional kind-specific name validator, called at register time BEFORE
    # persistence. Raises to reject the name. Used by `mcp_server` to reserve
    # the `__` tool/prompt namespace separator (CODE-030).
    validate_name: Callable[[str], None] | None = None
    # Optional semantic config validation beyond ``config_schema`` shape,
    # applied at REGISTRATION only (already shape-validated). Given the validated
    # config dict; raises ``ValueError`` to reject the write (e.g. a channel's
    # workspace directories must exist on disk). Deliberately not run on
    # update_config, so editing an unrelated field never re-probes the filesystem.
    validate_config: Callable[[dict[str, Any]], None] | None = None
    # Optional pre-write hook for ``ResourceService.update_config``.
    # Receives ``(ref, before_config, after_config)`` (both already shape-validated
    # against ``config_schema``); raises ``ConfigValidationError`` to reject the
    # update. Unlike ``validate_config`` it knows WHICH resource is being edited.
    # Only `channel` supplies one today: it re-validates ``default_agent``
    # against the live agent registry and against the channel's own scope, so
    # an edit cannot bind the channel to an agent it may not drive. Sync or
    # async; the service awaits an Awaitable.
    on_update_config: (
        Callable[
            [ResourceRef, dict[str, Any], dict[str, Any]],
            Awaitable[None] | None,
        ]
        | None
    ) = None
    # Optional PRE-write hook for ``ResourceService.update_scope`` (ADR per-agent-resource-scope):
    # given the resource as it currently stands and the scope proposed for it,
    # raise ``ValueError`` to reject the edit before anything is persisted. The
    # kind-agnostic path converts that into ``ScopeInvalidError``, so the API
    # answer has the same shape as a malformed-payload rejection and a kind
    # never names a surface-level error code.
    #
    # It is the scope path's counterpart to ``on_update_config`` — the same
    # "the kind gets a say before a write" precedent — and deliberately fires at
    # the opposite end of the operation from ``on_scope_changed`` in the
    # reactions section below; ``resource_scope_ops`` explains why the two differ.
    #
    # Only `channel` supplies one today: its scope names the agents it may
    # DRIVE, so a narrowing that excluded its own ``default_agent`` would store
    # a row the runtime then refuses to start. Rejecting it here is what keeps
    # that invariant true on BOTH write paths (config and scope) rather than
    # only on the config one. Sync or async; the service awaits an Awaitable.
    validate_scope_for: (
        Callable[
            [Resource, Scope | None],
            Awaitable[None] | None,
        ]
        | None
    ) = None
    # Optional kind-supplied credential-ref extractor: given a validated config
    # dict, return ``{logical_key: keychain_ref}``. ResourceService probes each
    # ref at register/update time so a missing credential fails before any DB
    # write — without the core knowing where a kind stores its refs.
    credential_ref_extractor: Callable[[dict[str, Any]], dict[str, str]] | None = None
    # Optional kind-supplied audit redactor: given a validated config dict,
    # return an audit-safe copy with secret-bearing fields stripped. Keeps the
    # kind-agnostic ResourceService from hardcoding any one kind's config shape
    # (e.g. mcp_server's ``transport.env``/``headers``) — resource framework / CODE-006.
    # A pure transform of the config consulted when the audit event is built;
    # it never rejects a write.
    audit_redactor: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    # Optional kind-supplied starting scope, consulted ONCE by
    # ``ResourceService.register`` (ADR per-agent-resource-scope). Given the validated config,
    # returns the scope the new row is created with; ``None`` keeps the
    # framework default (unscoped — active for every agent).
    #
    # It exists for a kind whose "every agent" default would be WRONG rather
    # than merely wide: `provider` pre-fills the wire's own projection default
    # (an ollama connection projects into no agent at all), so a newly created
    # connection behaves exactly as it did when that default lived inside its
    # config. A kind for which "every agent until narrowed" is right — every
    # other one today — supplies nothing.
    #
    # It is deliberately a function of the CONFIG alone, so the kind-agnostic
    # register path can call it with what it already has. A kind whose starting
    # scope depends on something outside the config — `memory` defaults to the
    # agents a partition was aggregated FROM (spec memory FR-014) — cannot use
    # this hook and sets the scope itself right after registering.
    default_scope: Callable[[dict[str, Any]], Scope | None] | None = None

    # --- Post-write reactions: run AFTER persistence + audit; cannot reject ---

    # Cleanup for ``ResourceService.delete``. The one exception to "after": it
    # runs BEFORE the row is removed so cleanup can still resolve the row — but
    # it is a reaction to an already-decided delete, not a validator, and has
    # no way to reject it. The hook may return ``None`` (purely synchronous) or
    # an ``Awaitable``; the kind-agnostic ResourceService awaits the result when
    # present so cleanup completes before the row is removed (a fire-and-forget
    # task would race the delete and find a ResourceNotFound on follow-up reads).
    on_delete: Callable[[ResourceRef], Awaitable[None] | None] | None = None
    # Optional post-write hook for ``ResourceService.update_scope`` (ADR per-agent-resource-scope).
    # Receives the ref whose scope just changed; invoked AFTER persistence +
    # audit (unlike ``on_update_config``, which runs BEFORE — scope
    # reconciliation needs to read the already-persisted scope), so it cannot
    # reject the edit, only react to it. Sync or async; the service awaits an
    # Awaitable. Kind-level side effect that keeps delivery/reclaim in step
    # with a scope edit, so a user editing scope in the UI/CLI sees it applied
    # immediately instead of waiting on an unrelated trigger.
    on_scope_changed: (
        Callable[
            [ResourceRef],
            Awaitable[None] | None,
        ]
        | None
    ) = None
    # Optional post-write hook for ``ResourceService.set_enabled``, the exact
    # mirror of ``on_scope_changed``: same signature, same sync-or-async
    # convention, and likewise invoked AFTER persistence + audit so a hook that
    # re-reads the resource sees the new ``enabled`` value. A kind whose
    # ``enabled`` flag has an on-disk consequence rather than a read-time one
    # wires it here — `skill` uses it so disabling a skill reclaims its
    # delivered copies and re-enabling redelivers them. (`mcp_server` needs no
    # hook: its gateway filters on ``enabled`` at read time.)
    on_enabled_changed: (
        Callable[
            [ResourceRef],
            Awaitable[None] | None,
        ]
        | None
    ) = None

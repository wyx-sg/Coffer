"""Core Resource domain entities.

A resource's identity is its **``uid``** — an opaque, immutable string minted
once and never reused (ADR resource-identity-is-an-immutable-uid).
Its ``name`` is a mutable label: unique within its kind, because a user should
not have two skills called the same thing, but uniqueness is a constraint and
not an identity. Everything that has to keep pointing at the same resource
across a rename — a cross-resource reference, a synced document, a URL — holds
the uid.

``id`` is the integer surrogate primary key. It is the foreign key four
kind-owned tables hold, it never leaves the process, and it is NOT the uid: it
is a row number, so two machines allocate the same one to different resources.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from coffer.domain.scope import Scope

#: A name is still a single safe path segment. The identity no longer needs it
#: to be — a uid addresses the row and names the synced document — but three
#: kinds (`skill`, `knowledge`, `memory`) turn a name into a directory, so the
#: rule survives as a property of the label rather than of the identity.
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]+$")
_NAME_MAX_LEN = 64


class InvalidResourceNameError(ValueError):
    """A proposed name is not a usable label."""


def validate_resource_name(name: str) -> None:
    """Raise :class:`InvalidResourceNameError` unless ``name`` is a usable label.

    The one place the rule lives, called by every write path that accepts a
    name — registration and rename alike — so the two cannot drift apart the
    way they did while rename was one kind's private operation.
    """
    if not name:
        raise InvalidResourceNameError("name must not be empty")
    if len(name) > _NAME_MAX_LEN:
        raise InvalidResourceNameError(
            f"name too long ({len(name)} chars, max {_NAME_MAX_LEN}): {name!r}"
        )
    if not _NAME_PATTERN.match(name):
        raise InvalidResourceNameError(f"invalid name {name!r}: must match ^[a-zA-Z0-9_.-]+$")


@dataclass
class Resource:
    """A user-managed entity inside Coffer.

    Resources share the kind-agnostic shape; kind-specific behaviour
    lives in services keyed off the `kind` field.
    """

    #: Integer surrogate primary key — internal, per-machine, never serialised.
    id: int
    #: The identity: opaque, immutable, the same value on every machine that
    #: holds this resource. Everything outside the process addresses this.
    uid: str
    kind: str
    #: A mutable label, unique within ``kind``.
    name: str
    description: str | None
    config: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime
    # Framework-level activation scope (ADR per-agent-resource-scope): one
    # allow-list of agent UIDS. None means unscoped (active for every agent) —
    # the pre-scope default, so every existing constructor keeps working
    # unchanged. Scope is machine-local: it is set on the machine it applies to
    # and does not travel with the vault (spec vault-sync ``## What does not
    # sync``). Interpreted via coffer.domain.scope; only kinds whose
    # Kind.supports_scope is True may set it (validate_scope).
    scope: Scope | None = None


@dataclass(frozen=True)
class Kind:
    """Pure descriptor of a resource kind.

    Held by ResourceService; lookup-only. Each kind's ``make_<kind>_kind()``
    factory in ``application/<kind>/kind.py`` returns one of these. Surface
    artefacts (HTTP routers, Typer groups) are NOT carried here: the
    composition root registers them itself through its per-kind wiring
    modules (``surfaces/http/<kind>_wiring.py`` and ``surfaces/cli/main.py``),
    so the domain layer never references a surface.

    Every hook below is handed the ``Resource`` it concerns rather than an
    identifier to look it up with. That is what replaced the old
    ``ResourceRef``: a hook that needs the kind, the name or the config has it
    already, and one that needs the identity reads ``resource.uid``.
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
    # `mcp_server`, `skill`, `channel` and `provider` set this True; `agent`
    # deliberately does not — it IS the agent, so there is nothing for a
    # per-agent scope to narrow — and `knowledge`/`memory` withdrew from reach
    # in migration 0088.
    supports_scope: bool = False
    # Whether this kind's rows converge with the sync remote (spec vault-sync).
    # True for everything the user authored — the rows a second machine is
    # supposed to receive. False for a kind whose rows are DERIVED from what is
    # installed on one machine: publishing those produces, at the other end, a
    # row naming something that machine does not have, with nothing behind it,
    # which the next local pass would recompute away anyway. `memory` is the
    # only kind that sets it False today (spec memory FR-016). Declared here
    # rather than listed in the exporter so the sync layer keeps one rule
    # instead of a table of exceptions — the shape the retired machine-local
    # kind list had.
    converges: bool = True
    # Optional per-ROW refinement of ``converges`` above: given a row's config,
    # answer whether THAT row travels. Consulted only when ``converges`` is
    # True — the flag can withhold a whole kind, this can withhold one row of a
    # kind that otherwise travels, and neither can put back what the other
    # held. Absent (the default) means the flag alone decides.
    #
    # It exists because a kind can carry both authored rows and derived ones.
    # `skill` does: almost every skill is a bundle a person imported, and those
    # are exactly what a second machine is supposed to receive — but Coffer's
    # own `coffer-guide` is written by the running build from the live
    # knowledge catalogue and this machine's own switches, re-rendered at every
    # boot. Publishing it is publishing derived output: two machines with the
    # same files but a different set of collections enabled render different
    # bytes, overwrite each other every round, and never stop. The reasoning is
    # ``memory``'s (spec memory FR-023) applied to one row instead of a kind,
    # so it is declared the same way — on the kind, beside the flag it refines
    # — rather than as a name the sync layer would have to recognise.
    #
    # A function of the CONFIG alone, like ``default_scope`` and
    # ``audit_redactor``, so every caller can ask it with what it already has:
    # the exporter holds a ``Resource``, while the sync applier holds only a
    # document that has just arrived and has no row behind it yet.
    converges_row: Callable[[dict[str, Any]], bool] | None = None

    # --- Pre-write validators: run BEFORE persistence; raising rejects the write ---

    # Optional kind-specific name validator, called BEFORE persistence by every
    # path that sets a name — registration AND rename. Raises to reject the
    # name. Used by `mcp_server` to reserve the `__` tool/prompt namespace
    # separator (CODE-030).
    validate_name: Callable[[str], None] | None = None
    # Optional semantic config validation beyond ``config_schema`` shape,
    # applied at REGISTRATION only (already shape-validated). Given the validated
    # config dict; raises ``ValueError`` to reject the write (e.g. a channel's
    # workspace directories must exist on disk). Deliberately not run on
    # update_config, so editing an unrelated field never re-probes the filesystem.
    # Sync or async; the service awaits an Awaitable — `channel` needs the
    # resource table to answer whether its `default_agent` uid names a
    # registered agent, and that question cannot be asked synchronously.
    validate_config: (
        Callable[
            [dict[str, Any]],
            Awaitable[None] | None,
        ]
        | None
    ) = None
    # Optional pre-write hook for ``ResourceService.update_config``.
    # Receives ``(resource_as_it_stands, proposed_config)`` (the proposal already
    # shape-validated against ``config_schema``); raises ``ConfigValidationError``
    # to reject the update. Unlike ``validate_config`` it knows WHICH resource is
    # being edited — and, since it is handed the resource, what it currently says.
    # Only `channel` supplies one today: it re-validates ``default_agent``
    # against the live agent registry and against the channel's own scope, so
    # an edit cannot bind the channel to an agent it may not drive. Sync or
    # async; the service awaits an Awaitable.
    on_update_config: (
        Callable[
            [Resource, dict[str, Any]],
            Awaitable[None] | None,
        ]
        | None
    ) = None
    # Optional PRE-write hook for ``ResourceService.rename``, and the whole of
    # what a rename costs a kind. It runs after the new name has been validated
    # and checked for collision, and BEFORE the row moves; raising aborts the
    # rename with nothing changed.
    #
    # It exists because three kinds keep a directory named after the resource —
    # `skill` (~/.coffer/skills/<name>), `knowledge` and `memory` — and the
    # directory has to travel with the label. The four config-only kinds supply
    # nothing and rename by writing one column.
    #
    # Pre-write, like ``on_delete``, so a move that cannot happen stops the
    # rename instead of leaving a row pointing at a directory that is not there.
    # The reverse ordering has one residual window — a racing writer could claim
    # the new name between the collision check and the commit, leaving a moved
    # directory under a name the row never took — which the service closes by
    # asking the hook to move it back.
    on_rename: (
        Callable[
            [Resource, str],
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
    # Optional pre-write guard for ``ResourceService.delete``: given the
    # resource about to be removed, raise to refuse the deletion before
    # anything is torn down. It sits with the other pre-write validators rather
    # than with ``on_delete`` below deliberately — ``on_delete`` is a reaction
    # to an already-decided delete, and a kind that refuses from inside it
    # refuses only after the caller has been told the delete is under way.
    #
    # Only `skill` supplies one today: a builtin skill's master folder is
    # rewritten by the next boot, so deleting it is a no-op dressed as a
    # destructive action. Raising ``ResourceProtected`` turns it into an honest
    # 409 on every surface at once — the kind's own DELETE and the
    # kind-agnostic one — rather than one guard per route, which is the shape
    # that lets a second route quietly miss it.
    validate_delete: Callable[[Resource], None] | None = None

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
    # register path can call it with what it already has.
    default_scope: Callable[[dict[str, Any]], Scope | None] | None = None

    # --- Post-write reactions: run AFTER persistence + audit; cannot reject ---

    # Cleanup for ``ResourceService.delete``. The one exception to "after": it
    # runs BEFORE the row is removed so cleanup can still resolve the row — but
    # it is a reaction to an already-decided delete, not a validator, and has
    # no way to reject it. The hook may return ``None`` (purely synchronous) or
    # an ``Awaitable``; the kind-agnostic ResourceService awaits the result when
    # present so cleanup completes before the row is removed (a fire-and-forget
    # task would race the delete and find a ResourceNotFound on follow-up reads).
    on_delete: Callable[[Resource], Awaitable[None] | None] | None = None
    # Optional post-write hook for ``ResourceService.update_scope`` (ADR per-agent-resource-scope).
    # Receives the resource whose scope just changed, as persisted (unlike
    # ``on_update_config``, which runs BEFORE — scope reconciliation needs to
    # read the already-persisted scope), so it cannot reject the edit, only
    # react to it. Sync or async; the service awaits an Awaitable. Kind-level
    # side effect that keeps delivery/reclaim in step with a scope edit, so a
    # user editing scope in the UI/CLI sees it applied immediately instead of
    # waiting on an unrelated trigger.
    on_scope_changed: (
        Callable[
            [Resource],
            Awaitable[None] | None,
        ]
        | None
    ) = None
    # Optional post-write hook for ``ResourceService.set_enabled``, the exact
    # mirror of ``on_scope_changed``: same signature, same sync-or-async
    # convention, and likewise invoked AFTER persistence + audit so the hook is
    # handed the row carrying the new ``enabled`` value. A kind whose
    # ``enabled`` flag has an on-disk consequence rather than a read-time one
    # wires it here — `skill` uses it so disabling a skill reclaims its
    # delivered copies and re-enabling redelivers them. (`mcp_server` needs no
    # hook: its gateway filters on ``enabled`` at read time.)
    on_enabled_changed: (
        Callable[
            [Resource],
            Awaitable[None] | None,
        ]
        | None
    ) = None

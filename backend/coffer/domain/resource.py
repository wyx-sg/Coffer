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

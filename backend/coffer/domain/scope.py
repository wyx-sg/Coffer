"""Framework-level activation scope: one allow-list of agents (ADR per-agent-resource-scope).

A resource's ``scope`` names the agents it activates for:

- ``None``                          — active for every agent (the default)
- ``{"agents": ["claude-code"]}``   — only for that agent
- ``{"agents": []}``                — dormant (an empty list matches nothing)

Unknown names are legal and simply never match, so a resource can be scoped to
an agent that has not been registered yet.

**There is no machine axis, and there is nothing for one to say.** A resource's
activation state is machine-local: it is set on the machine it applies to and
does not travel (spec vault-sync ``## What does not sync``). Each machine
therefore names the resources it activates by *holding* that scope, and writing
machine ids inside the scope as well would be the same fact recorded twice —
with two places to disagree. A resource that should be live on the desktop and
dark on the laptop is now expressed by setting it that way on each, which is
also the only expression a user can verify from the machine they are sitting at.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ScopeValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Scope:
    """One optional allow-list. ``None`` means unrestricted."""

    agents: list[str] | None = None

    def to_json(self) -> dict[str, Any]:
        return {"agents": self.agents}

    @classmethod
    def from_json(cls, raw: Any) -> Scope | None:
        """Parse a persisted ``scope_json`` payload.

        The machine-axis removal migration rewrote every row into the
        single-axis shape, so this accepts only that shape — there is no
        fallback keeping a stale row limping, because a migration is a one-time
        event and leaves no load-time shim behind.
        """
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ScopeValidationError("scope must be an object with an agents list, or null")
        return cls(agents=_axis(raw.get("agents")))


def _axis(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ScopeValidationError("a scope axis must be a list of names or null")
    for name in value:
        if not isinstance(name, str) or not name:
            raise ScopeValidationError("scope entries must be non-empty names")
    return list(value)


def is_active(scope: Scope | None, agent: str | None) -> bool:
    """Whether a resource carrying ``scope`` activates for this agent.

    An unrestricted scope matches anything; a restricted one needs a name. An
    unidentified session (``agent is None`` — a hand-configured shim that
    reports no ``--agent``) matches only an unrestricted scope, so it sees
    strictly less, never more.
    """
    if scope is None or scope.agents is None:
        return True
    return agent is not None and agent in scope.agents


def validate_scope(scope: object, *, supports_scope: bool) -> None:
    """Reject a scope payload the kind can't carry.

    ``supports_scope=False`` (the default for kinds that declare none) admits
    only ``None``; anything else is a 422 at the front door.
    """
    if scope is None:
        return
    if not supports_scope:
        raise ScopeValidationError("this kind does not support scope")
    if isinstance(scope, Scope):
        return
    Scope.from_json(scope)

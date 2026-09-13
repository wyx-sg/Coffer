"""Framework-level activation scope: two axes, ``AND``-ed (ADR per-agent-resource-scope).

A resource's ``scope`` names where it activates, along two independent axes:

- ``None``                              — active everywhere (the default)
- ``{"agents": ["claude-code"]}``       — only for that agent, on any machine
- ``{"machines": ["a3f2…"]}``           — only on that machine, for any agent
- both                                  — only where both match
- ``{"agents": []}``                    — dormant (an empty list matches nothing)

An axis left ``None`` is unrestricted; an axis given a list restricts to it.
Unknown names in either list are legal and simply never match, so a resource
can be scoped to an agent or a machine that has not appeared yet.

The machine axis returned with bidirectional sync (spec vault-sync). It is keyed by
the derived ``machine_id``, never by the display name, so renaming a machine
costs nothing. It is deliberately **not** a matrix of (machine, agent) pairs:
the only thing a matrix adds is naming a different agent per machine on one
resource, which nothing needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Which axis kept a resource dormant here, for a UI that has to explain itself.
ExclusionAxis = str  # "agent" | "machine"


class ScopeValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Scope:
    """Two optional allow-lists. ``None`` on an axis means unrestricted."""

    agents: list[str] | None = None
    machines: list[str] | None = None

    def to_json(self) -> dict[str, Any]:
        return {"agents": self.agents, "machines": self.machines}

    @classmethod
    def from_json(cls, raw: Any) -> Scope | None:
        """Parse a persisted ``scope_json`` payload.

        The scope-reshape migration rewrote every row into the two-axis
        shape, so this accepts only that shape — there is no
        list-of-agent-names fallback keeping a stale row limping, because a
        migration is a one-time event and leaves no load-time shim behind.
        """
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ScopeValidationError("scope must be an object with agents/machines, or null")
        return cls(agents=_axis(raw.get("agents")), machines=_axis(raw.get("machines")))


def _axis(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ScopeValidationError("a scope axis must be a list of names or null")
    for name in value:
        if not isinstance(name, str) or not name:
            raise ScopeValidationError("scope entries must be non-empty names")
    return list(value)


def _axis_matches(allowed: list[str] | None, value: str | None) -> bool:
    """An unrestricted axis matches anything; a restricted one needs a name.

    An unidentified session (``value is None`` — a hand-configured shim that
    reports no ``--agent``) matches only an unrestricted axis, so it sees
    strictly less, never more.
    """
    if allowed is None:
        return True
    return value is not None and value in allowed


def is_active(scope: Scope | None, *, agent: str | None, machine: str | None) -> bool:
    """Whether a resource carrying ``scope`` activates for this agent here."""
    return excluded_by(scope, agent=agent, machine=machine) is None


def excluded_by(
    scope: Scope | None, *, agent: str | None, machine: str | None
) -> ExclusionAxis | None:
    """Which axis kept the resource dormant, or None when it is active.

    The machine axis is reported first: a resource dormant on this whole
    machine is a different thing to explain than one dormant for one agent,
    and it is the answer the user is more likely to be looking for.
    """
    if scope is None:
        return None
    if not _axis_matches(scope.machines, machine):
        return "machine"
    if not _axis_matches(scope.agents, agent):
        return "agent"
    return None


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


def agent_axis_admits(scope: Scope | None, agent: str | None) -> bool:
    """Whether the AGENT axis alone admits ``agent``, ignoring machines.

    Almost every caller wants ``is_active`` (both axes, through a
    ``ScopeEvaluator`` that already holds this machine's id). This exists for
    the handful of seams where re-applying the machine axis would answer a
    question nobody asked:

    - the channel routing seams — `/agent`'s listing and card, the per-turn
      agent, a new conversation's agent — which only ever execute on a machine
      whose runtime gate already admitted the channel, so asking again could
      only return the same yes at the cost of every seam needing a machine id.
    - ``provider``'s configured reach, which is a statement about agent types
      and must read the same on every machine of a converged vault.

    The channel kind's two write-path validators answer the same question but
    read ``scope.agents`` directly, because they need the list itself for the
    rejection message. Their reason for ignoring the machine axis is stronger
    still: a channel scoped to another machine has to stay editable from here,
    or a converged vault could hold a channel nobody can correct.

    The ``agent is None`` rule is the one in ``_axis_matches``: an unidentified
    session matches only an unrestricted axis, so it sees strictly less.
    """
    return scope is None or _axis_matches(scope.agents, agent)

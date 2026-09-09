"""Framework-level per-agent activation scope (ADR-045).

A resource's ``scope`` is a plain list of agent names:

- ``None``          — active for every agent (the pre-scope default)
- ``[]``            — active for no agent (dormant)
- ``["claude-code"]`` — active only for the named agents

Unknown agent names in the list are legal and simply never match, so a
resource can be scoped in before that agent is registered. The machine axis
this module once carried was withdrawn with continuous multi-machine sync
(ADR-016): without a machine registry there are no machine identities for it
to name.
"""

from __future__ import annotations

Scope = list[str]


class ScopeValidationError(ValueError):
    pass


def agent_in_scope(scope: Scope | None, agent: str | None) -> bool:
    """Whether ``agent`` may activate a resource carrying ``scope``.

    An unidentified session (``agent is None`` — a hand-configured shim that
    reports no ``--agent``) matches only an unscoped resource, so it sees
    strictly less, never more.
    """
    if scope is None:
        return True
    return agent is not None and agent in scope


def validate_scope(scope: object, *, supports_scope: bool) -> None:
    """Reject a scope payload the kind can't carry.

    ``supports_scope=False`` (the default for kinds that declare none) admits
    only ``None``; anything else is a 422 at the front door.
    """
    if scope is None:
        return
    if not supports_scope:
        raise ScopeValidationError("this kind does not support scope")
    if not isinstance(scope, list):
        raise ScopeValidationError("scope must be a list of agent names or null")
    for agent in scope:
        if not isinstance(agent, str) or not agent:
            raise ScopeValidationError("scope entries must be non-empty agent names")

"""Framework-level machine × agent activation scope (ADR-045)."""

from __future__ import annotations

ScopeValue = list[str] | str
Scope = dict[str, ScopeValue]
WILDCARD = "*"


class ScopeValidationError(ValueError):
    pass


def _entry(scope: Scope, machine_id: str) -> ScopeValue | None:
    if machine_id in scope:
        return scope[machine_id]
    return scope.get(WILDCARD)


def machine_in_scope(scope: Scope | None, machine_id: str) -> bool:
    if scope is None:
        return True
    value = _entry(scope, machine_id)
    if value is None:
        return False
    return value == WILDCARD or len(value) > 0


def agent_in_scope(scope: Scope | None, machine_id: str, agent: str | None) -> bool:
    if scope is None:
        return True
    value = _entry(scope, machine_id)
    if value is None:
        return False
    if value == WILDCARD:
        return True
    return agent is not None and agent in value


def validate_scope(scope: object, *, axes: tuple[str, ...]) -> None:
    if scope is None:
        return
    if not axes:
        raise ScopeValidationError("this kind does not support scope")
    if not isinstance(scope, dict):
        raise ScopeValidationError("scope must be a mapping or null")
    for key, value in scope.items():
        if not isinstance(key, str) or not key:
            raise ScopeValidationError("scope keys must be machine ids or '*'")
        if value == WILDCARD:
            continue
        if "agent" not in axes:
            raise ScopeValidationError("machine-scoped kind accepts only '*' values")
        if not isinstance(value, list) or any(not isinstance(a, str) or not a for a in value):
            raise ScopeValidationError("scope values must be '*' or a list of agent names")

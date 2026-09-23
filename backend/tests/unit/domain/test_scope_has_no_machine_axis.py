"""A scope names agents and nothing else (spec vault-sync "Scope names agents only").

Reach is machine-local, so a machine already says which resources it activates
by holding that scope; a machine axis inside it would record the same fact
twice. What a scope means is read through ``is_active``; what a scope may carry
is decided at the wire, where a client still sending ``machines`` is refused
rather than silently widened to every agent.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coffer.domain.scope import Scope, is_active
from coffer.surfaces.http.schemas import ResourceScopeUpdate, ScopeOut

_AGENTS = ("uid-claude", "uid-codex", "uid-cursor")


@pytest.mark.acceptance(spec="vault-sync", scenario="a scope names agents and nothing else")
def test_a_scope_matches_agents_and_carries_no_machine_axis() -> None:
    every = None
    listed = Scope.from_json({"agents": ["uid-claude", "uid-codex"]})
    dormant = Scope.from_json({"agents": []})
    unknown = Scope.from_json({"agents": ["uid-not-registered-here"]})

    assert all(is_active(every, a) for a in _AGENTS)
    assert [a for a in _AGENTS if is_active(listed, a)] == ["uid-claude", "uid-codex"]
    assert not any(is_active(dormant, a) for a in _AGENTS)
    # Legal — it parsed above without complaint — and simply never matches.
    assert unknown is not None and unknown.agents == ["uid-not-registered-here"]
    assert not any(is_active(unknown, a) for a in _AGENTS)

    # The wire shape is `{agents: [...]}` and nothing else.
    assert ScopeOut(agents=["uid-claude"]).model_dump() == {"agents": ["uid-claude"]}
    for machine_axis in (
        {"agents": ["uid-claude"], "machines": ["a1a1a1a1a1a1a1a1"]},
        {"agents": None, "machines": None},
    ):
        with pytest.raises(ValidationError):
            ScopeOut.model_validate(machine_axis)
        with pytest.raises(ValidationError):
            ResourceScopeUpdate.model_validate({"scope": machine_axis})

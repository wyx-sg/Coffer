"""Activation-scope semantics (ADR per-agent-resource-scope, two axes).

``scope`` is two independent allow-lists, ``AND``-ed: the agent asking and the
machine it is asking on. Each axis left ``None`` is unrestricted, which is why
the machine axis could be added to every existing row by addition alone (spec
vault-sync, "Scope gains a machine axis").
"""

import pytest

from coffer.domain.scope import (
    Scope,
    ScopeValidationError,
    excluded_by,
    is_active,
    validate_scope,
)

HERE = "a3f21c9e4b7d2610"
ELSEWHERE = "0f0f0f0f0f0f0f0f"


def test_none_scope_is_active_everywhere():
    assert is_active(None, agent="claude-code", machine=HERE) is True
    assert is_active(None, agent=None, machine=None) is True


def test_null_axes_are_unrestricted():
    everywhere = Scope(agents=None, machines=None)
    assert is_active(everywhere, agent="claude-code", machine=HERE) is True
    assert is_active(everywhere, agent=None, machine=None) is True


def test_empty_axis_matches_nothing():
    assert is_active(Scope(agents=[]), agent="claude-code", machine=HERE) is False
    assert is_active(Scope(machines=[]), agent="claude-code", machine=HERE) is False


def test_agent_axis_alone():
    scope = Scope(agents=["claude-code"])
    assert is_active(scope, agent="claude-code", machine=HERE) is True
    # Any machine, since that axis is unrestricted.
    assert is_active(scope, agent="claude-code", machine=ELSEWHERE) is True
    assert is_active(scope, agent="codex", machine=HERE) is False


def test_machine_axis_alone():
    scope = Scope(machines=[HERE])
    # Any agent, since that axis is unrestricted.
    assert is_active(scope, agent="claude-code", machine=HERE) is True
    assert is_active(scope, agent="codex", machine=HERE) is True
    assert is_active(scope, agent="claude-code", machine=ELSEWHERE) is False


def test_both_axes_are_anded():
    scope = Scope(agents=["claude-code"], machines=[HERE])
    assert is_active(scope, agent="claude-code", machine=HERE) is True
    assert is_active(scope, agent="codex", machine=HERE) is False
    assert is_active(scope, agent="claude-code", machine=ELSEWHERE) is False
    assert is_active(scope, agent="codex", machine=ELSEWHERE) is False


def test_unknown_machine_id_is_dormant():
    # Exactly as an unknown agent name already was: legal to write, never
    # matches, so a resource can be scoped to a machine not yet registered.
    scope = Scope(machines=["not-registered-yet"])
    validate_scope(scope, supports_scope=True)
    assert is_active(scope, agent="claude-code", machine=HERE) is False


def test_unknown_agent_names_are_legal_and_never_match():
    scope = {"agents": ["not-installed-yet"]}
    validate_scope(scope, supports_scope=True)
    assert is_active(Scope.from_json(scope), agent="claude-code", machine=HERE) is False


def test_unidentified_session_only_matches_an_unrestricted_agent_axis():
    # A shim reporting no ``--agent`` sees strictly less, never more.
    assert is_active(Scope(agents=["claude-code"]), agent=None, machine=HERE) is False
    assert is_active(Scope(machines=[HERE]), agent=None, machine=HERE) is True


def test_excluded_by_names_the_axis():
    assert excluded_by(None, agent="claude-code", machine=HERE) is None
    assert excluded_by(Scope(agents=["codex"]), agent="claude-code", machine=HERE) == "agent"
    assert excluded_by(Scope(machines=[ELSEWHERE]), agent="claude-code", machine=HERE) == "machine"


def test_excluded_by_prefers_machine_over_agent():
    """Dormant on this whole machine is the answer the user is looking for."""
    both_wrong = Scope(agents=["codex"], machines=[ELSEWHERE])
    assert excluded_by(both_wrong, agent="claude-code", machine=HERE) == "machine"


# --- round-tripping the persisted shape ------------------------------------


def test_to_json_emits_both_axes():
    assert Scope(agents=["claude-code"]).to_json() == {
        "agents": ["claude-code"],
        "machines": None,
    }


def test_from_json_round_trip():
    for scope in (
        Scope(),
        Scope(agents=[]),
        Scope(agents=["claude-code", "codex"]),
        Scope(machines=[HERE]),
        Scope(agents=["claude-code"], machines=[HERE, ELSEWHERE]),
    ):
        assert Scope.from_json(scope.to_json()) == scope


def test_from_json_null_is_unscoped():
    assert Scope.from_json(None) is None


def test_from_json_rejects_the_retired_list_shape():
    # Migration 0069 rewrote every row; a list reaching here is a bug, not a
    # legacy row to be tolerated (a migration leaves no load-time shim).
    with pytest.raises(ScopeValidationError):
        Scope.from_json(["claude-code"])


# --- validation ------------------------------------------------------------


def test_kind_without_scope_rejects_non_null():
    with pytest.raises(ScopeValidationError):
        validate_scope({"agents": ["claude-code"]}, supports_scope=False)
    with pytest.raises(ScopeValidationError):
        validate_scope(Scope(agents=[]), supports_scope=False)
    # Clearing scope is always allowed, even for a kind that has none.
    validate_scope(None, supports_scope=False)


def test_scope_supporting_kind_accepts_both_shapes():
    validate_scope(None, supports_scope=True)
    validate_scope(Scope(agents=["claude-code"]), supports_scope=True)
    validate_scope({"agents": [], "machines": None}, supports_scope=True)
    validate_scope({"machines": [HERE]}, supports_scope=True)


def test_validate_rejects_malformed():
    for bad in (
        "claude-code",
        1,
        ["claude-code"],
        {"agents": "claude-code"},
        {"agents": ["ok", 1]},
        {"machines": [""]},
        {"machines": [None]},
    ):
        with pytest.raises(ScopeValidationError):
            validate_scope(bad, supports_scope=True)

import pytest
from coffer.domain.scope import (
    ScopeValidationError,
    agent_in_scope,
    machine_in_scope,
    validate_scope,
)

M = "01HXXXXXXXXXXXXXXXXXXXXXXX"


def test_none_scope_is_active_everywhere():
    assert machine_in_scope(None, M)
    assert agent_in_scope(None, M, "claude-code")
    assert agent_in_scope(None, M, None)


def test_empty_scope_is_dormant_everywhere():
    assert not machine_in_scope({}, M)
    assert not agent_in_scope({}, M, "claude-code")


def test_exact_machine_key_wins_over_wildcard():
    scope = {"*": "*", M: ["codex"]}
    assert agent_in_scope(scope, M, "codex")
    assert not agent_in_scope(scope, M, "claude-code")
    assert agent_in_scope(scope, "01HOTHER" + "X" * 18, "claude-code")


def test_unidentified_agent_matches_only_star():
    assert agent_in_scope({M: "*"}, M, None)
    assert not agent_in_scope({M: ["claude-code"]}, M, None)


def test_machine_in_scope_requires_nonempty_value():
    assert machine_in_scope({M: "*"}, M)
    assert machine_in_scope({M: ["a"]}, M)
    assert not machine_in_scope({M: []}, M)
    assert not machine_in_scope({"other": "*"}, M)  # no wildcard key present


def test_validate_rejects_scope_on_axisless_kind():
    with pytest.raises(ScopeValidationError):
        validate_scope({}, axes=())
    validate_scope(None, axes=())


def test_validate_machine_only_kind_rejects_agent_lists():
    with pytest.raises(ScopeValidationError):
        validate_scope({M: ["claude-code"]}, axes=("machine",))
    validate_scope({M: "*"}, axes=("machine",))


def test_validate_rejects_malformed():
    for bad in ("x", 1, {1: "*"}, {M: "all"}, {M: [1]}):
        with pytest.raises(ScopeValidationError):
            validate_scope(bad, axes=("machine", "agent"))

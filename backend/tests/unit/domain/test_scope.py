"""Activation-scope semantics (ADR per-agent-resource-scope, one axis).

``scope`` is a single allow-list: the agent asking, **by uid**. There is no
machine axis — a resource's activation state is machine-local, so the machine
that holds the scope *is* the machine answer, and naming machine ids inside it
would record the same fact twice.

The entries are uids and not agent names, which is why none of the literals
below look like something a user typed. While the list held names, renaming an
agent silently emptied every scope that named it; a uid cannot change
underneath a reference (ADR resource-identity-is-an-immutable-uid).
"""

import pytest

from coffer.domain.scope import (
    Scope,
    ScopeValidationError,
    is_active,
    validate_scope,
)

# Two agent uids. Opaque on purpose: nothing may infer which agent a uid is.
_A = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
_B = "1122334455667788990011223344556677"


def test_none_scope_is_active_for_every_agent():
    assert is_active(None, _A) is True
    assert is_active(None, None) is True


def test_null_axis_is_unrestricted():
    everywhere = Scope(agents=None)
    assert is_active(everywhere, _A) is True
    assert is_active(everywhere, None) is True


def test_empty_list_is_dormant():
    """An empty allow-list matches nothing — that is how a resource is parked."""
    assert is_active(Scope(agents=[]), _A) is False
    assert is_active(Scope(agents=[]), None) is False


def test_a_list_admits_only_what_it_names():
    scope = Scope(agents=[_A])
    assert is_active(scope, _A) is True
    assert is_active(scope, _B) is False


def test_unknown_agent_uids_are_legal_and_never_match():
    # Legal to write, so a resource can be scoped to an agent this machine does
    # not have; it simply stays dormant until that agent exists here.
    scope = {"agents": ["deadbeefdeadbeefdeadbeefdeadbeef"]}
    validate_scope(scope, supports_scope=True)
    assert is_active(Scope.from_json(scope), _A) is False


def test_unidentified_session_only_matches_an_unrestricted_scope():
    # A shim reporting no ``--agent-uid`` sees strictly less, never more.
    assert is_active(Scope(agents=[_A]), None) is False
    assert is_active(Scope(agents=[]), None) is False
    assert is_active(Scope(agents=None), None) is True


# --- round-tripping the persisted shape ------------------------------------


def test_to_json_emits_the_single_axis():
    assert Scope(agents=[_A]).to_json() == {"agents": [_A]}
    assert Scope().to_json() == {"agents": None}


def test_from_json_round_trip():
    for scope in (
        Scope(),
        Scope(agents=[]),
        Scope(agents=[_A, _B]),
    ):
        assert Scope.from_json(scope.to_json()) == scope


def test_from_json_null_is_unscoped():
    assert Scope.from_json(None) is None


def test_from_json_rejects_anything_but_an_object():
    # Migration 0076 rewrote every row into the single-axis shape; a list or a
    # bare string reaching here is a bug, not a legacy row to be tolerated (a
    # migration leaves no load-time shim).
    for bad in ([_A], _A, 1):
        with pytest.raises(ScopeValidationError):
            Scope.from_json(bad)


def test_from_json_rejects_non_string_entries():
    for bad in ({"agents": _A}, {"agents": [_A, 1]}, {"agents": [""]}):
        with pytest.raises(ScopeValidationError):
            Scope.from_json(bad)


# --- validation ------------------------------------------------------------


def test_kind_without_scope_rejects_non_null():
    with pytest.raises(ScopeValidationError):
        validate_scope({"agents": [_A]}, supports_scope=False)
    with pytest.raises(ScopeValidationError):
        validate_scope(Scope(agents=[]), supports_scope=False)
    # Clearing scope is always allowed, even for a kind that has none.
    validate_scope(None, supports_scope=False)


def test_scope_supporting_kind_accepts_both_shapes():
    validate_scope(None, supports_scope=True)
    validate_scope(Scope(agents=[_A]), supports_scope=True)
    validate_scope({"agents": []}, supports_scope=True)
    validate_scope({"agents": None}, supports_scope=True)


def test_validate_rejects_malformed():
    for bad in (
        _A,
        1,
        [_A],
        {"agents": _A},
        {"agents": [_A, 1]},
        {"agents": [None]},
    ):
        with pytest.raises(ScopeValidationError):
            validate_scope(bad, supports_scope=True)

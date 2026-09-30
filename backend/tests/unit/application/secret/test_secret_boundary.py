"""The secret boundary's rules, over in-memory tables (spec secret).

"Hold a secret for a new destination until a person approves it", "Hold a
replaced value in use until a person approves it", "Turn the protection off
only through the desktop app".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.secret.boundary import SecretBoundary
from coffer.domain.secret_errors import ApprovalNotPending, SecretBindingPending
from coffer.domain.secrets import SecretDestination
from tests.support.secret_boundary import FakeSealedValues, InMemoryBoundaryStore

_OLD = datetime.now(tz=UTC) - timedelta(days=30)


def _dest(uid: str, target: str) -> SecretDestination:
    return SecretDestination(kind="mcp_server", uid=uid, target=target, label=uid)


def _gate() -> tuple[SecretBoundary, InMemoryBoundaryStore, FakeSealedValues]:
    store, values = InMemoryBoundaryStore(), FakeSealedValues()
    return SecretBoundary(store, values), store, values


@pytest.mark.acceptance(
    spec="secret", scenario="a value supplied for its destination needs no approval"
)
def test_a_value_stored_moments_ago_for_an_unbound_ref_is_approved() -> None:
    gate, store, values = _gate()
    values.put("mcp_server/a/TOKEN", "v")

    gate.require(_dest("a", "stdio server-a"), {"TOKEN": "mcp_server/a/TOKEN"})

    assert [b.destination_uid for b in store.bindings()] == ["a"]


def test_an_old_unbound_ref_is_not_fresh() -> None:
    gate, _store, values = _gate()
    values.put("gh/token", "v", created=_OLD)

    with pytest.raises(SecretBindingPending):
        gate.require(_dest("a", "stdio a"), {"TOKEN": "gh/token"})


def test_a_standalone_secret_is_never_fresh() -> None:
    gate, _store, values = _gate()
    values.put("secret/db-password", "v")

    with pytest.raises(SecretBindingPending):
        gate.require(_dest("a", "stdio a"), {"PW": "secret/db-password"})


def test_a_second_destination_for_a_bound_ref_waits_and_the_first_keeps_working() -> None:
    gate, _store, values = _gate()
    values.put("gh/token", "v")
    gate.require(_dest("a", "stdio a"), {"TOKEN": "gh/token"})

    pending = gate.check(_dest("b", "stdio evil.sh"), {"TOKEN": "gh/token"}, actor="agent")

    assert len(pending) == 1
    assert pending[0].target == "stdio evil.sh" and pending[0].requested_by == "agent"
    # Asking again records nothing new: one approval per target.
    assert [a.id for a in gate.check(_dest("b", "stdio evil.sh"), {"TOKEN": "gh/token"})] == [
        pending[0].id
    ]
    gate.require(_dest("a", "stdio a"), {"TOKEN": "gh/token"})


def test_a_new_target_supersedes_the_approval_for_the_old_one_and_approval_applies() -> None:
    gate, _store, values = _gate()
    values.put("gh/token", "v", created=_OLD)
    first = gate.check(_dest("a", "stdio one"), {"TOKEN": "gh/token"})[0]
    second = gate.check(_dest("a", "stdio two"), {"TOKEN": "gh/token"})[0]

    assert gate.get(first.id).status == "superseded"
    gate.approve(second.id, actor="desktop")
    gate.require(_dest("a", "stdio two"), {"TOKEN": "gh/token"})
    with pytest.raises(SecretBindingPending):
        gate.require(_dest("a", "stdio three"), {"TOKEN": "gh/token"})


def test_an_approval_is_decided_once() -> None:
    gate, _store, values = _gate()
    values.put("gh/token", "v", created=_OLD)
    waiting = gate.check(_dest("a", "stdio a"), {"TOKEN": "gh/token"})[0]
    gate.reject(waiting.id, actor="cli")

    with pytest.raises(ApprovalNotPending):
        gate.approve(waiting.id, actor="desktop")


def test_adoption_approves_what_is_in_use_once() -> None:
    gate, store, values = _gate()
    values.put("gh/token", "v", created=_OLD)
    current = [(_dest("a", "stdio a"), {"TOKEN": "gh/token"}, "user")]

    assert gate.adopt(current) == 1
    assert gate.adopt([(_dest("b", "stdio b"), {"TOKEN": "gh/token"}, "user")]) == 0
    gate.require(_dest("a", "stdio a"), {"TOKEN": "gh/token"})
    assert len(store.bindings()) == 1


def test_refresh_supersedes_an_approval_nothing_asks_for() -> None:
    gate, _store, values = _gate()
    values.put("gh/token", "v", created=_OLD)
    waiting = gate.check(_dest("gone", "stdio x"), {"TOKEN": "gh/token"})[0]

    gate.refresh([])

    assert gate.get(waiting.id).status == "superseded"


@pytest.mark.acceptance(spec="secret", scenario="replacing a value in use waits for approval")
def test_replacing_a_value_in_use_holds_it_sealed_until_approved() -> None:
    gate, store, values = _gate()
    values.put("gh/token", "old")
    gate.require(_dest("a", "stdio a"), {"TOKEN": "gh/token"})

    approval = gate.write("gh/token", "new-value", actor="agent")

    assert approval is not None and approval.op == "replace_value"
    assert values.get("gh/token") == "old"
    assert b"new-value" not in store.sealed[approval.id]
    gate.approve(approval.id, actor="desktop")
    assert values.get("gh/token") == "new-value"
    assert approval.id not in store.sealed


def test_writing_a_new_or_unbound_ref_applies_at_once() -> None:
    gate, _store, values = _gate()
    assert gate.write("new/ref", "v", actor="cli") is None
    assert values.get("new/ref") == "v"
    assert gate.write("new/ref", "v2", actor="cli") is None
    assert values.get("new/ref") == "v2"


@pytest.mark.acceptance(spec="secret", scenario="adding a standalone secret waits for approval")
def test_adding_a_standalone_secret_holds_it_sealed_until_approved() -> None:
    gate, store, values = _gate()

    approval = gate.write("secret/npm-publish-token", "npm-value", actor="ui")

    assert approval is not None and approval.op == "add_secret"
    assert approval.describe() == "add the new secret 'npm-publish-token'"
    assert not values.exists("secret/npm-publish-token")
    assert b"npm-value" not in store.sealed[approval.id]
    # A newer value for the same new secret replaces the one still waiting.
    newer = gate.write("secret/npm-publish-token", "npm-value-2", actor="ui")
    assert newer is not None and gate.get(approval.id).status == "superseded"
    gate.approve(newer.id, actor="desktop")
    assert values.get("secret/npm-publish-token") == "npm-value-2"


def test_a_rejected_new_secret_is_never_stored() -> None:
    gate, store, values = _gate()
    approval = gate.write("secret/npm-publish-token", "npm-value", actor="ui")
    assert approval is not None

    gate.reject(approval.id, actor="ui")

    assert not values.exists("secret/npm-publish-token")
    assert approval.id not in store.sealed


def test_with_protection_off_a_new_secret_is_stored_at_once() -> None:
    gate, _store, values = _gate()
    gate.approve(gate.request_disable("cli").id, actor="desktop")

    assert gate.write("secret/npm-publish-token", "v", actor="ui") is None
    assert values.get("secret/npm-publish-token") == "v"


@pytest.mark.acceptance(
    spec="secret", scenario="switching the protection off waits for the desktop app"
)
def test_switching_protection_off_takes_an_approval() -> None:
    gate, _store, values = _gate()
    values.put("gh/token", "v", created=_OLD)
    request = gate.request_disable("cli")

    assert gate.protections_on()
    assert gate.request_disable("cli").id == request.id
    gate.approve(request.id, actor="desktop")
    assert not gate.protections_on()
    gate.require(_dest("a", "stdio anything"), {"TOKEN": "gh/token"})

    gate.enable_protections()
    assert gate.protections_on()
    with pytest.raises(SecretBindingPending):
        gate.require(_dest("b", "stdio other"), {"TOKEN": "gh/token"})


def test_a_deleted_secret_forgets_where_it_went() -> None:
    gate, store, values = _gate()
    values.put("gh/token", "v")
    gate.require(_dest("a", "stdio a"), {"TOKEN": "gh/token"})
    gate.forget("gh/token")
    assert store.bindings() == []

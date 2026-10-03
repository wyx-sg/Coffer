"""The secret boundary's rules, over in-memory tables (spec secret).

"Hold a secret for a new destination until a person approves it", "Hold a
replaced value in use until a person approves it", "Turn the protection off
only through the desktop app".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.secret.boundary import SecretBoundary
from coffer.domain.secret_errors import (
    ApprovalNotPending,
    SecretBindingPending,
    SecretBindingRejected,
    SecretUnreadable,
)
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
def test_a_value_supplied_with_the_registration_is_approved_there() -> None:
    gate, store, values = _gate()
    values.put("mcp_server/a/TOKEN", "v")

    waiting = gate.bind(_dest("a", "stdio server-a"), {"TOKEN": "mcp_server/a/TOKEN"}, actor="ui")

    assert waiting == []
    assert [b.destination_uid for b in store.bindings()] == ["a"]
    gate.require(_dest("a", "stdio server-a"), {"TOKEN": "mcp_server/a/TOKEN"})


@pytest.mark.acceptance(
    spec="secret", scenario="a destination registered with a stored secret is settled at once"
)
def test_a_second_destination_cannot_borrow_a_value_supplied_for_the_first() -> None:
    gate, store, values = _gate()
    values.put("mcp_server/a/TOKEN", "v")
    # Bound to the first destination by its registration, before any use, so
    # nothing else can cite the value afterwards without a person.
    assert gate.bind(_dest("a", "stdio a"), {"TOKEN": "mcp_server/a/TOKEN"}, actor="ui") == []
    pending = gate.bind(_dest("b", "stdio evil.sh"), {"TOKEN": "mcp_server/a/TOKEN"}, actor="agent")

    assert [p.destination_uid for p in pending] == ["b"]
    assert [b.destination_uid for b in store.bindings()] == ["a"]
    with pytest.raises(SecretBindingPending):
        gate.require(_dest("b", "stdio evil.sh"), {"TOKEN": "mcp_server/a/TOKEN"})


def test_a_binding_met_only_at_use_is_never_supplied() -> None:
    gate, _store, values = _gate()
    values.put("mcp_server/a/TOKEN", "v")

    # Reached by a spawn or a listing, not by a registration: whatever arrived
    # behind Coffer's back waits for a person.
    with pytest.raises(SecretBindingPending):
        gate.require(_dest("a", "stdio a"), {"TOKEN": "mcp_server/a/TOKEN"})


def test_an_old_unused_value_is_not_supplied_for_a_destination_registered_now() -> None:
    gate, _store, values = _gate()
    values.put("gh/token", "v", created=_OLD)

    assert len(gate.bind(_dest("a", "stdio a"), {"TOKEN": "gh/token"}, actor="ui")) == 1


def test_a_ref_that_arrived_from_elsewhere_is_not_supplied() -> None:
    gate, _store, values = _gate()
    values.put("gh/token", "v")
    del values.created["gh/token"]  # a ciphertext this machine did not write

    assert len(gate.bind(_dest("a", "stdio a"), {"TOKEN": "gh/token"}, actor="ui")) == 1


def test_a_standalone_secret_is_never_supplied() -> None:
    gate, _store, values = _gate()
    values.put("secret/db-password", "v")

    assert len(gate.bind(_dest("a", "stdio a"), {"PW": "secret/db-password"}, actor="ui")) == 1


def test_a_target_change_waits_at_the_change() -> None:
    gate, _store, values = _gate()
    values.put("mcp_server/a/TOKEN", "v")
    gate.bind(_dest("a", "stdio one"), {"TOKEN": "mcp_server/a/TOKEN"}, actor="ui")

    pending = gate.bind(_dest("a", "stdio two"), {"TOKEN": "mcp_server/a/TOKEN"}, actor="agent")

    assert [p.target for p in pending] == ["stdio two"]


def test_a_second_destination_for_a_bound_ref_waits_and_the_first_keeps_working() -> None:
    gate, _store, values = _gate()
    values.put("gh/token", "v")
    gate.bind(_dest("a", "stdio a"), {"TOKEN": "gh/token"}, actor="ui")

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
    gate.bind(_dest("a", "stdio a"), {"TOKEN": "gh/token"}, actor="ui")

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
    gate.bind(_dest("a", "stdio a"), {"TOKEN": "gh/token"}, actor="ui")
    gate.forget("gh/token")
    assert store.bindings() == []


@pytest.mark.acceptance(
    spec="secret", scenario="a refused binding stays refused until its target changes"
)
def test_a_refused_binding_is_reported_as_refused_not_as_waiting() -> None:
    gate, _store, values = _gate()
    values.put("gh/token", "v", created=_OLD)
    dest = _dest("a", "stdio a")
    waiting = gate.check(dest, {"TOKEN": "gh/token"})[0]
    gate.reject(waiting.id, actor="ui")

    with pytest.raises(SecretBindingRejected) as refused:
        gate.require(dest, {"TOKEN": "gh/token"})

    assert refused.value.code == "SECRET_BINDING_REJECTED"
    assert refused.value.approval_ids == [waiting.id]
    # Still a withheld secret for every caller that handles the pending kind.
    assert isinstance(refused.value, SecretBindingPending)
    # Checking again raises no fresh approval: the refusal stands for this target.
    assert gate.check(dest, {"TOKEN": "gh/token"})[0].id == waiting.id


@pytest.mark.acceptance(
    spec="secret", scenario="a refused binding stays refused until its target changes"
)
def test_refresh_drops_a_refusal_of_a_target_that_has_changed() -> None:
    gate, _store, values = _gate()
    values.put("gh/token", "v", created=_OLD)
    old = _dest("a", "stdio one")
    refused = gate.check(old, {"TOKEN": "gh/token"})[0]
    gate.reject(refused.id, actor="ui")

    gate.refresh([(_dest("a", "stdio two"), {"TOKEN": "gh/token"}, "ui")])

    assert gate.get(refused.id).status == "superseded"
    # The changed target is put to a person afresh.
    assert [a.status for a in gate.list(status="pending")] == ["pending"]


@pytest.mark.acceptance(spec="secret", scenario="an approval that cannot be applied stays pending")
def test_an_approval_that_cannot_be_applied_stays_pending_with_its_sealed_value() -> None:
    gate, store, values = _gate()
    approval = gate.write("secret/npm-publish-token", "npm-value", actor="ui")
    assert approval is not None

    def broken(_token: bytes) -> str:
        raise SecretUnreadable("<pending replacement>")

    values.unseal = broken  # type: ignore[method-assign]
    with pytest.raises(SecretUnreadable):
        gate.approve(approval.id, actor="desktop")

    assert gate.get(approval.id).status == "pending"
    assert approval.id in store.sealed

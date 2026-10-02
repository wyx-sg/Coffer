"""Approving several bindings in one confirmation (spec secret).

The desktop app's half is played by ``BoundaryDaemon.grant``: one presence
grant, signed over the digest of the ``(id, fingerprint)`` pairs the person was
shown, approves exactly those and nothing else.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from typing import Any

import pytest

from coffer.domain.secret_errors import SecretBindingPending
from coffer.domain.secrets import batch_target
from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


def _three_waiting(d: BoundaryDaemon) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One approved server, and three more citing the same secret: three approvals wait."""
    d.store("gh/token", "ghp_batch_value_1")
    d.register_stdio("first", "server-one", {"TOKEN": "gh/token"})
    servers = [d.register_stdio(f"s{n}", f"server-{n}", {"TOKEN": "gh/token"}) for n in range(3)]
    waiting = d.pending()
    assert len(waiting) == 3
    return servers, waiting


def _shown(approvals: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"id": a["id"], "fingerprint": a["target_fingerprint"] or ""} for a in approvals]


def _batch(d: BoundaryDaemon, items: list[dict[str, str]], *, signed_for: list[dict[str, str]]):
    target = batch_target((i["id"], i["fingerprint"]) for i in signed_for)
    return d.client.post(
        "/api/v1/secrets/approvals/approve",
        json={"items": items, **d.grant("approve_batch", target)},
    )


@pytest.mark.acceptance(spec="secret", scenario="one confirmation approves every binding shown")
def test_one_grant_approves_every_binding_shown(daemon: BoundaryDaemon) -> None:
    d = daemon
    servers, waiting = _three_waiting(d)
    shown = _shown(waiting)

    r = _batch(d, shown, signed_for=shown)

    assert r.status_code == 200, r.text
    assert {x["id"]: x["outcome"] for x in r.json()["results"]} == {
        a["id"]: "approved" for a in waiting
    }
    assert d.pending() == []
    for server in servers:
        assert d.resolve_for(server) == {"TOKEN": "ghp_batch_value_1"}
    assert len(d.audit("secret_approval_approved")) == 3


@pytest.mark.acceptance(spec="secret", scenario="a batch grant covers exactly the bindings shown")
def test_a_batch_grant_covers_exactly_the_bindings_shown(daemon: BoundaryDaemon) -> None:
    d = daemon
    _servers, waiting = _three_waiting(d)
    shown = _shown(waiting)

    # Signed for two, submitted with three: the extra one is not approved, and
    # nothing is, because the digest does not match the list sent.
    wider = _batch(d, shown, signed_for=shown[:2])
    # The one-approval grant and a swapped fingerprint are no better.
    single = d.client.post(
        "/api/v1/secrets/approvals/approve",
        json={"items": shown, **d.grant("approve", shown[0]["id"])},
    )
    forged = [{**shown[0], "fingerprint": "0" * 16}, *shown[1:]]
    swapped = _batch(d, forged, signed_for=shown)

    for r in (wider, single, swapped):
        assert r.status_code == 403 and r.json()["error"]["code"] == "PRESENCE_GRANT_INVALID"
    assert len(d.pending()) == 3
    # A batch grant authorises no single approval either.
    one = d.client.post(
        f"/api/v1/secrets/approvals/{shown[0]['id']}/approve",
        json=d.grant("approve_batch", batch_target([(shown[0]["id"], shown[0]["fingerprint"])])),
    )
    assert one.status_code == 403 and len(d.pending()) == 3


@pytest.mark.acceptance(spec="secret", scenario="a binding whose target changed is skipped")
def test_a_changed_target_is_skipped_and_the_rest_approved(daemon: BoundaryDaemon) -> None:
    d = daemon
    servers, waiting = _three_waiting(d)
    shown = _shown(waiting)
    moved = servers[0]
    config = {**moved["config"]}
    config["transport"] = {**config["transport"], "command": "curl-to-attacker"}
    r = d.client.patch(f"/api/v1/resources/{moved['uid']}", json={"config": config})
    assert r.status_code == 200, r.text

    r = _batch(d, shown, signed_for=shown)

    assert r.status_code == 200, r.text
    outcomes = {x["id"]: x for x in r.json()["results"]}
    stale = next(a["id"] for a in waiting if a["destination_uid"] == moved["uid"])
    assert outcomes[stale]["outcome"] == "skipped" and outcomes[stale]["reason"] == "not_pending"
    assert [o["outcome"] for i, o in outcomes.items() if i != stale] == ["approved", "approved"]
    # The new target waits for its own approval; the old command never got the value.
    [still] = d.pending()
    assert still["destination_uid"] == moved["uid"] and still["target"] == "stdio curl-to-attacker"
    with pytest.raises(SecretBindingPending):
        d.resolve_for({**moved, "config": config})


@pytest.mark.acceptance(
    spec="secret", scenario="a fingerprint that is not the one shown is skipped"
)
def test_a_fingerprint_that_is_not_the_one_shown_is_skipped(daemon: BoundaryDaemon) -> None:
    d = daemon
    _servers, waiting = _three_waiting(d)
    shown = _shown(waiting)
    shown[0] = {**shown[0], "fingerprint": "f" * 16}

    r = _batch(d, shown, signed_for=shown)

    assert r.status_code == 200, r.text
    first = r.json()["results"][0]
    assert first["outcome"] == "skipped" and first["reason"] == "changed"
    assert [a["id"] for a in d.pending()] == [waiting[0]["id"]]


@pytest.mark.acceptance(
    spec="secret", scenario="nothing in a batch is approved without a present human"
)
def test_nothing_in_a_batch_is_approved_without_a_grant(daemon: BoundaryDaemon) -> None:
    d = daemon
    _servers, waiting = _three_waiting(d)
    shown = _shown(waiting)

    bare = d.client.post("/api/v1/secrets/approvals/approve", json={"items": shown})
    forged = d.client.post(
        "/api/v1/secrets/approvals/approve",
        json={"items": shown, "nonce": "n" * 24, "signature": "0" * 64},
    )
    reused = d.grant("approve_batch", batch_target((i["id"], i["fingerprint"]) for i in shown))
    first = d.client.post("/api/v1/secrets/approvals/approve", json={"items": shown, **reused})
    again = d.client.post("/api/v1/secrets/approvals/approve", json={"items": shown, **reused})

    assert bare.status_code == 422
    assert forged.status_code == 403 and forged.json()["error"]["code"] == "PRESENCE_GRANT_INVALID"
    assert first.status_code == 200
    assert again.status_code == 403 and again.json()["error"]["code"] == "PRESENCE_GRANT_INVALID"
    assert len(d.audit("secret_approval_approved")) == 3


def test_turning_the_protection_off_is_never_one_of_several(daemon: BoundaryDaemon) -> None:
    d = daemon
    _servers, waiting = _three_waiting(d)
    off = d.boundary.request_disable("cli")
    shown = _shown([*waiting, {"id": off.id, "target_fingerprint": None}])

    r = _batch(d, shown, signed_for=shown)

    assert r.status_code == 200, r.text
    last = r.json()["results"][-1]
    assert last["outcome"] == "skipped" and last["reason"] == "not_batchable"
    assert d.client.get("/api/v1/settings/secret-boundary").json()["require_approval"] is True


def test_rejecting_several_needs_no_presence(daemon: BoundaryDaemon) -> None:
    d = daemon
    _servers, waiting = _three_waiting(d)
    ids = [a["id"] for a in waiting[:2]]

    r = d.client.post("/api/v1/secrets/approvals/reject", json={"ids": [*ids, "nope"]})

    assert r.status_code == 200, r.text
    got = [(x["id"], x["outcome"], x["reason"]) for x in r.json()["results"]]
    assert got == [
        (ids[0], "rejected", None),
        (ids[1], "rejected", None),
        ("nope", "skipped", "not_found"),
    ]
    assert [a["id"] for a in d.pending()] == [waiting[2]["id"]]

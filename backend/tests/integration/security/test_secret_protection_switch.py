"""The secret-approval switch (Settings, Security tab): on at once, off only
through a presence grant, and told to the Overview while off.

Turning the protection on only narrows, so it needs nobody; turning it off
widens, so the request waits as a ``disable_protection`` approval that only the
desktop app can apply. The app's half is played by ``BoundaryDaemon.grant``.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest

from coffer.application.secret.boundary import SecretBoundary
from coffer.domain.secrets import batch_target
from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon

_URL = "/api/v1/settings/secret-boundary"


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


def _state(d: BoundaryDaemon) -> dict[str, object]:
    return d.client.get(_URL).json()


def _turn_off(d: BoundaryDaemon) -> str:
    r = d.client.put(_URL, json={"require_approval": False})
    assert r.status_code == 202, r.text
    return str(r.json()["pending_approval_id"])


def _attention_kinds(d: BoundaryDaemon) -> list[str]:
    r = d.client.get("/api/v1/attention")
    assert r.status_code == 200, r.text
    return [i["reason_code"] for i in r.json()["items"] if i["kind"] == "secret"]


def test_the_protection_is_on_by_default(daemon: BoundaryDaemon) -> None:
    assert _state(daemon) == {"require_approval": True, "pending_approval_id": None}
    assert _attention_kinds(daemon) == []


def test_turning_it_off_waits_and_changes_nothing_until_a_grant_applies_it(
    daemon: BoundaryDaemon,
) -> None:
    d = daemon
    approval_id = _turn_off(d)

    assert _state(d) == {"require_approval": True, "pending_approval_id": approval_id}
    # Asking again does not stack a second approval.
    assert _turn_off(d) == approval_id

    forged = {**d.grant("approve", approval_id), "signature": "0" * 64}
    without = d.client.post(f"/api/v1/secrets/approvals/{approval_id}/approve", json=forged)
    wrong_op = d.client.post(
        f"/api/v1/secrets/approvals/{approval_id}/approve", json=d.grant("reveal", approval_id)
    )
    for refused in (without, wrong_op):
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "PRESENCE_GRANT_INVALID"
    assert _state(d)["require_approval"] is True

    d.approve(approval_id)
    assert _state(d) == {"require_approval": False, "pending_approval_id": None}
    approved = [
        e for e in d.audit("secret_approval_approved") if e["details"]["op"] == "disable_protection"
    ]
    assert len(approved) == 1 and approved[0]["actor"] == "desktop"
    assert len(d.audit("secret_approval_requested")) >= 1


def test_the_switch_off_is_not_part_of_a_batch(daemon: BoundaryDaemon) -> None:
    d = daemon
    approval_id = _turn_off(d)
    shown = [{"id": approval_id, "fingerprint": ""}]
    grant = d.grant("approve_batch", batch_target((i["id"], i["fingerprint"]) for i in shown))
    r = d.client.post("/api/v1/secrets/approvals/approve", json={"items": shown, **grant})

    assert r.status_code == 200, r.text
    assert [(x["outcome"], x.get("reason")) for x in r.json()["results"]] == [
        ("skipped", "not_batchable")
    ]
    assert _state(d)["require_approval"] is True


def test_turning_it_on_needs_no_presence_and_is_audited_once(daemon: BoundaryDaemon) -> None:
    d = daemon
    d.approve(_turn_off(d))
    assert _attention_kinds(d) == ["secret_approval_off"]

    on = d.client.put(_URL, json={"require_approval": True})
    again = d.client.put(_URL, json={"require_approval": True})

    assert on.status_code == 200 and on.json()["require_approval"] is True
    assert again.status_code == 200
    assert _state(d)["require_approval"] is True
    assert len(d.audit("secret_protection_enabled")) == 1
    assert _attention_kinds(d) == []


def test_the_off_state_is_a_warning_with_a_turn_on_action(daemon: BoundaryDaemon) -> None:
    d = daemon
    d.approve(_turn_off(d))

    items = [i for i in d.client.get("/api/v1/attention").json()["items"] if i["kind"] == "secret"]

    assert len(items) == 1
    [item] = items
    assert item["severity"] == "warning"
    assert item["action"]["verb"] == "turn_on"
    assert item["action"]["method"] == "PUT" and item["action"]["path"].endswith("secret-boundary")
    assert item["action"]["body"] == {"require_approval": True}


def test_approvals_waiting_when_it_is_turned_off_stay_pending(daemon: BoundaryDaemon) -> None:
    d = daemon
    d.store("gh/token", "ghp_switch_value_1")
    d.register_stdio("first", "server-one", {"TOKEN": "gh/token"})
    second = d.register_stdio("second", "evil.sh", {"TOKEN": "gh/token"})
    [waiting] = d.pending(destination_uid=second["uid"])

    d.approve(_turn_off(d))

    assert _state(d)["require_approval"] is False
    still = d.client.get(f"/api/v1/secrets/approvals/{waiting['id']}").json()
    assert still["status"] == "pending"
    # A destination checked after the switch is off goes without asking; the one
    # that already waited was not approved on anyone's behalf.
    third = d.register_stdio("third", "other.sh", {"TOKEN": "gh/token"})
    assert d.resolve_for(third) == {"TOKEN": "ghp_switch_value_1"}


def test_the_setting_survives_a_restart_of_the_boundary(daemon: BoundaryDaemon) -> None:
    d = daemon
    d.approve(_turn_off(d))
    # A fresh boundary over the same tables reads the stored setting.
    fresh = SecretBoundary(d.boundary._store, d.boundary._values)
    assert fresh.protections_on() is False

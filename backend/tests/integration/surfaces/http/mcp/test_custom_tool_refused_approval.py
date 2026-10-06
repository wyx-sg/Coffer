"""A custom-tool group whose secret binding a person refused (spec mcp-gateway
"Wait for approval before a custom tool sends its secret", secret "Hold a
secret for a new destination until a person approves it").

A refusal is not a wait: the group says it was refused, nothing asks the person
until someone asks again, and asking again puts a new request up.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon
from tests.support.custom_tools import SECRET_NAME, create_group, get_group, tool
from tests.support.fake_http_api import FakeHttpApi, fake_http_api


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


@pytest.fixture
def api() -> Iterator[FakeHttpApi]:
    with fake_http_api() as a:
        yield a


def _refused_group(d: BoundaryDaemon, api: FakeHttpApi) -> str:
    """A group whose one approval a person refused; answers the refused id."""
    create_group(
        d, "billing", api.base_url, [tool("list_invoices", "GET", "/invoices")], approve=False
    )
    [approval_id] = get_group(d, "billing")["pending_approvals"]
    r = d.client.post(f"/api/v1/secrets/approvals/{approval_id}/reject")
    assert r.status_code == 200, r.text
    return str(approval_id)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a refused binding shows as refused, not waiting"
)
def test_a_refused_binding_shows_as_refused_not_waiting(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    refused = _refused_group(daemon, api)
    group = get_group(daemon, "billing")
    assert group["secret_state"] == "rejected"
    assert (group["health"], group["health_reason"]) == ("attention", "approval_rejected")
    assert group["pending_approvals"] == [] and group["pending_secrets"] == []
    assert group["rejected_approvals"] == [refused]
    assert group["rejected_secrets"] == [SECRET_NAME]
    [env] = group["environments"]
    assert env["secret_state"] == "rejected" and env["rejected_approvals"] == [refused]
    assert {h["secret_state"] for h in env["headers"] if h["secret"]} == {"rejected"}
    assert daemon.pending() == []

    r = daemon.client.post(f"/api/v1/secrets/approvals/{refused}/ask-again")
    assert r.status_code == 200, r.text
    [asked] = r.json()["approvals"]
    assert asked["status"] == "pending" and asked["id"] != refused
    group = get_group(daemon, "billing")
    assert group["secret_state"] == "pending_approval"
    assert group["pending_approvals"] == [asked["id"]] and group["rejected_approvals"] == []


@pytest.mark.acceptance(
    spec="secret", scenario="asking again after a refusal puts the request back"
)
def test_asking_again_after_a_refusal_puts_the_request_back(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    refused = _refused_group(daemon, api)
    r = daemon.client.post(f"/api/v1/secrets/approvals/{refused}/ask-again")
    assert r.status_code == 200, r.text
    [asked] = r.json()["approvals"]
    old = daemon.client.get(f"/api/v1/secrets/approvals/{refused}").json()
    assert old["status"] == "superseded"
    assert (asked["ref"], asked["destination_uid"], asked["slot"], asked["target"]) == (
        old["ref"], old["destination_uid"], old["slot"], old["target"],
    )  # fmt: skip
    assert [a["id"] for a in daemon.pending()] == [asked["id"]]
    requested = daemon.audit("secret_approval_requested")
    assert any(e["details"]["approval_id"] == asked["id"] for e in requested)

    again = daemon.client.post(f"/api/v1/secrets/approvals/{asked['id']}/ask-again")
    assert again.status_code == 409, again.text
    assert again.json()["error"]["code"] == "APPROVAL_NOT_PENDING"

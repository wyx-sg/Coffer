"""A rollback's plan and the user name a remote check sends (spec vault-sync)."""

from __future__ import annotations

import pytest

import coffer.surfaces.http.sync_stop_routes  # noqa: F401  (registers the rollback routes)

from .conftest import client_for
from .harness import Box

DOC = "knowledge/team/on-call.md"


@pytest.mark.acceptance(spec="vault-sync", scenario="a rollback shows its plan first")
def test_the_plan_names_what_it_reverses_and_changes_nothing(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    mac.put(DOC, "Rotates on Tuesdays.\n")
    mac.round()
    pulled = mini.round()
    with client_for(mini) as c:
        plan = c.get(f"/sync/runs/{pulled.id}/rollback-plan")
        assert plan.status_code == 200, plan.text
        reversed_paths = {change["path"] for change in plan.json()["reverses"]}
        assert DOC in reversed_paths
        assert mini.disk(DOC) == b"Rotates on Tuesdays.\n"

        done = c.post(f"/sync/runs/{pulled.id}/rollback")
        assert done.status_code == 200, done.text
        assert mini.disk(DOC) == b"Primary on-call rotates every Monday.\n"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a remote check sends the user name it is given"
)
def test_a_remote_check_sends_the_given_user_name_else_the_stored_one(
    pair: tuple[Box, Box], monkeypatch: pytest.MonkeyPatch
) -> None:
    mac, _mini = pair
    seen: list[str] = []
    check = mac.service.check_remote

    async def spy(url, branch, secret_ref, username):  # type: ignore[no-untyped-def]
        seen.append(username)
        return await check(url, branch, secret_ref, username)

    monkeypatch.setattr(mac.service, "check_remote", spy)
    with client_for(mac) as c:
        body = c.get("/sync/remote").json()["remote"]
        base = {"url": body["url"], "branch": body["branch"]}
        assert c.post("/sync/remote/check", json={**base, "username": "oauth2"}).status_code == 200
        assert c.post("/sync/remote/check", json=base).status_code == 200
    assert seen[0] == "oauth2"
    assert seen[1] == body["username"]

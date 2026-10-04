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
def test_a_remote_check_sends_the_user_name_its_host_implies(
    pair: tuple[Box, Box], monkeypatch: pytest.MonkeyPatch
) -> None:
    mac, _mini = pair
    seen: list[str | None] = []

    def probe(url, branch, token, username=None):  # type: ignore[no-untyped-def]
        seen.append(username)
        return None

    monkeypatch.setattr(mac.service._probe, "probe", probe)
    with client_for(mac) as c:
        for url in (
            "https://gitlab.example.com/me/vault.git",
            "https://bitbucket.org/me/vault.git",
        ):
            checked = c.post("/sync/remote/check", json={"url": url, "branch": "main"})
            assert checked.status_code == 200, checked.text
    assert seen == ["oauth2", "x-token-auth"]

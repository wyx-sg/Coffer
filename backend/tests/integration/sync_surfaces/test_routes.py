"""/api/v1/sync over a real round (spec vault-sync): every route a Sync page
board reads or acts through."""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.domain.sync.remote import SyncRemote

from .conftest import client_for
from .harness import Box

DOC = "knowledge/team/on-call.md"


def _conflict(mac: Box, mini: Box) -> None:
    mac.put(DOC, "Mac rotates on Mondays.\n")
    mac.round()
    mini.put(DOC, "Mini rotates on Fridays.\n")


@pytest.mark.acceptance(spec="vault-sync", scenario="every round is recorded with what it moved")
def test_status_run_and_history(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    mac.put("knowledge/team/deploy.md", "Deploy on Tuesdays.\n")
    with client_for(mac) as c:
        status = c.get("/sync/status").json()
        assert status["configured"] and status["joined"]
        assert status["waiting"][0]["changes"] == [
            {"path": "knowledge/team/deploy.md", "status": "added"}
        ]
        assert status["areas"]["knowledge_documents"] == 2
        run = c.post("/sync/run").json()
        assert run["status"] == "pushed" and run["pushed_files"] == 1
        page = c.get("/sync/runs", params={"limit": 1}).json()
        assert page["rounds"][0]["id"] == run["id"] and page["total"] >= 1
        assert c.get(f"/sync/runs/{run['id']}").json()["status"] == "pushed"
        missing = c.get("/sync/runs/9999")
        assert missing.json()["error"]["code"] == "SYNC_ROUND_NOT_FOUND"


@pytest.mark.acceptance(spec="vault-sync", scenario="every round is recorded with what it moved")
def test_history_pages_by_cursor_without_repeating_or_skipping(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    with client_for(mac) as c:
        ids = [c.post("/sync/run").json()["id"] for _ in range(5)]
        first = c.get("/sync/runs", params={"limit": 2}).json()
        assert [r["id"] for r in first["rounds"]] == ids[:2:-1] and first["total"] >= 5
        # A round finishing at the head between two reads does not shift page 2.
        newest = c.post("/sync/run").json()["id"]
        second = c.get("/sync/runs", params={"limit": 2, "cursor": first["next_cursor"]}).json()
        assert [r["id"] for r in second["rounds"]] == ids[2:0:-1]
        assert newest not in [r["id"] for r in second["rounds"]]
        seen = [r["id"] for r in first["rounds"] + second["rounds"]]
        cursor = second["next_cursor"]
        while cursor:
            page = c.get("/sync/runs", params={"limit": 2, "cursor": cursor}).json()
            seen += [r["id"] for r in page["rounds"]]
            cursor = page["next_cursor"]
        assert len(seen) == len(set(seen)) == c.get("/sync/runs").json()["total"] - 1
        assert c.get("/sync/runs", params={"cursor": "junk"}).status_code == 400


@pytest.mark.acceptance(
    spec="vault-sync", scenario="keeping this machine's version continues the round"
)
def test_a_stop_is_answered_and_continued(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    _conflict(mac, mini)
    with client_for(mini) as c:
        assert c.post("/sync/run").json()["status"] == "stopped"
        state = c.get("/sync/stop").json()
        assert state["stopped"] and state["round"]["kind"] == "conflicts"
        (f,) = state["round"]["files"]
        assert (f["path"], f["reason"], f["theirs_machine"]) == (DOC, "both_changed", "Mac")
        versions = c.get("/sync/stop/files/versions", params={"path": DOC}).json()
        assert versions["theirs"] == "Mac rotates on Mondays.\n"
        editor = c.post("/sync/stop/files/editor", json={"path": DOC}).json()
        assert Path(editor["editor_path"]).is_file()
        refused = c.post("/sync/stop/files/answer", json={"path": DOC, "answer": "edited"})
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "SYNC_CONFLICT_MARKERS_LEFT"
        answered = c.post("/sync/stop/files/answer", json={"path": DOC, "answer": "mine"}).json()
        assert answered["round"]["unanswered"] == 0
        done = c.post("/sync/continue").json()
        assert done["status"] in ("pushed", "pulled_and_pushed", "pulled")
        assert c.get("/sync/stop").json() == {"stopped": False, "round": None}
        unknown = c.post("/sync/stop/files/answer", json={"path": DOC, "answer": "mine"})
        assert unknown.status_code == 409
    assert mini.disk(DOC) == b"Mini rotates on Fridays.\n"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an oversized deletion is held for confirmation"
)
def test_a_hold_is_confirmed_through_the_route(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    paths = [f"knowledge/bulk/n{i:02}.md" for i in range(22)]
    for p in paths:
        mac.put(p, p)
    mac.round()
    mac.remove(*paths)
    with client_for(mac) as c:
        assert c.post("/sync/run").json()["status"] == "held"
        hold = c.get("/sync/stop").json()["round"]["hold"]
        assert hold["direction"] == "outgoing"
        assert hold["groups"] == [{"folder": "knowledge/bulk", "paths": sorted(paths), "total": 22}]
        assert c.post("/sync/hold/confirm").json()["status"] == "pushed"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a remote URL or branch that git would read as an option is refused"
)
@pytest.mark.acceptance(spec="vault-sync", scenario="sync stays off until a remote is configured")
def test_remote_machines_join_and_key_routes(pair: tuple[Box, Box], tmp_path: Path) -> None:
    mac, _mini = pair
    with client_for(mac) as c:
        remote = c.get("/sync/remote").json()
        assert remote["configured"] and remote["remote"]["include_secret"] is False
        check = c.post("/sync/remote/check", json={"url": mac.url}).json()
        assert (check["result"], check["layout"]) == ("vault", 3)
        bad = c.put("/sync/remote", json={"url": "-upload-pack=evil"})
        assert bad.status_code == 422
        put = c.put("/sync/remote", json={"url": mac.url, "interval_seconds": 600}).json()
        assert put["interval_seconds"] == 600

        machines = c.get("/sync/machines").json()["machines"]
        assert [m["is_self"] for m in machines] == [True, False]
        renamed = c.patch("/sync/machines/self", json={"name": "Studio"}).json()
        assert renamed["name"] == "Studio" and renamed["is_self"]
        refused = c.delete("/sync/machines/mac")
        assert refused.status_code == 422
        assert c.delete("/sync/machines/mini").json() == {"removed": True}

        preview = c.get("/sync/join/preview").json()
        assert preview["kind"] in ("returning", "new")
        assert c.get("/sync/join-choices").json() == {"files": []}
        assert c.get("/sync/key/fingerprint").json() == {"fingerprint": "abc123abc123"}
        preview = c.post("/sync/key/import/preview", json={"material": "ok-key"}).json()
        assert preview == {
            "fingerprint": "f11e" * 3,
            "current_fingerprint": "abc123abc123",
            "same": False,
            "protected": False,
        }
        key = c.post("/sync/key/import", json={"material": "ok-key"}).json()
        assert key == {
            "fingerprint": "abc123abc123",
            "replaced": False,
            "readable": 0,
            "locked_refs": [],
        }

        assert c.delete("/sync/remote").json() == {"cleared": True, "restorable": True}
        no_remote = c.post("/sync/run")
        assert no_remote.json()["error"]["code"] == "SYNC_NO_REMOTE"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a round that applied nothing has nothing to roll back"
)
@pytest.mark.acceptance(spec="vault-sync", scenario="a round can be rolled back")
def test_a_round_is_rolled_back_through_the_route(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    mac.put(DOC, "Rotates on Tuesdays.\n")
    mac.round()
    with client_for(mini) as c:
        pulled = c.post("/sync/run").json()
        plan = c.get(f"/sync/runs/{pulled['id']}/rollback-plan").json()
        assert plan["reverses"] == [{"path": DOC, "status": "modified"}]
        assert plan["snapshot"].startswith("coffer/pre-apply/")
        rolled = c.post(f"/sync/runs/{pulled['id']}/rollback").json()
        assert rolled["status"] == "rolled_back"
        again = c.get(f"/sync/runs/{rolled['id']}/rollback-plan")
        assert again.status_code == 409
    assert mini.disk(DOC) == b"Primary on-call rotates every Monday.\n"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="the status counts commits ahead of and behind the remote"
)
def test_status_counts_commits_ahead_of_and_behind_the_remote(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    mac.put("knowledge/team/deploy.md", "Deploy on Tuesdays.\n")
    with client_for(mac) as c:
        status = c.get("/sync/status").json()
        assert (status["ahead"], status["behind"]) == (1, 0)
        c.post("/sync/run")
        status = c.get("/sync/status").json()
        assert (status["ahead"], status["behind"]) == (0, 0)
    mini.put("knowledge/team/oncall.md", "Rotate weekly.\n")
    with client_for(mini) as c:
        c.post("/sync/run")
    # Fetched, not yet merged: the remote has a commit this vault lacks.
    mac.git.fetch(SyncRemote(url=mac.url).branch, None)
    with client_for(mac) as c:
        status = c.get("/sync/status").json()
        assert (status["ahead"], status["behind"]) == (0, 1)

"""An agent's merge of a conflicting file (spec vault-sync "Hand conflicting files to
an agent"): the hand-off, the merged state read off the copy, marking
it resolved, going back to the two choices, and the same for a join's
differing files."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from coffer.domain.sync.rounds import RoundStatus
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.sync_dependencies import set_sync_service

from .conftest import TOKEN, client_for
from .harness import Box, fleet

DOC = "knowledge/team/on-call.md"
OTHER = "knowledge/team/runbook.md"
MERGED = "Both rotate: Mac on Mondays, Mini on Fridays.\n"


@pytest.fixture(autouse=True)
def _token() -> Iterator[None]:
    set_active_token(TOKEN)
    yield
    set_active_token(None)
    set_sync_service(None)


def _conflict(mac: Box, mini: Box) -> None:
    mac.put(DOC, "Mac rotates on Mondays.\n")
    mac.round()
    mini.put(DOC, "Mini rotates on Fridays.\n")


def _file(c: object, path: str = DOC, *, join: bool = False) -> dict[str, object]:
    got = c.get("/sync/join-choices" if join else "/sync/stop").json()  # type: ignore[attr-defined]
    files = got["files"] if join else got["round"]["files"]
    (found,) = [f for f in files if f["path"] == path]
    return found  # type: ignore[no-any-return]


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="an agent's merge is shown to be checked and marked resolved",
)
def test_an_agents_merge_is_checked_and_marked_resolved(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    _conflict(mac, mini)
    with client_for(mini) as c:
        assert c.post("/sync/run").json()["status"] == "stopped"
        file = _file(c)
        assert file["agent_mergeable"] is True and file["agent_state"] is None

        got = c.post("/sync/stop/handoff", json={}).json()
        assert got["paths"] == [DOC]
        prompt = got["handoff"]["prompt"]
        copy = Path(_file(c)["editor_path"])  # type: ignore[arg-type]
        assert DOC in prompt and str(copy) in prompt and str(mini.repo.root) in prompt
        assert "Mac" in prompt and "Mini" in prompt
        assert "git -C" not in prompt and "coffer sync" not in prompt, "no hard-coded commands"
        assert b"<<<<<<<" in copy.read_bytes()
        file = _file(c)
        assert file["agent_state"] == "handed_off" and file["agent_handed_at"]
        handed_at = file["agent_handed_at"]

        # The conversation the caller opened is attached without a second hand-off.
        c.post(
            "/sync/stop/handoff",
            json={"paths": [DOC], "agent": "Claude Code", "conversation_id": "conv-1"},
        )
        file = _file(c)
        assert (file["agent_name"], file["agent_conversation_id"]) == ("Claude Code", "conv-1")
        assert file["agent_handed_at"] == handed_at and file["agent_state"] == "handed_off"

        # Nothing merged yet, and marking the markers resolved is refused.
        versions = c.get("/sync/stop/files/versions", params={"path": DOC}).json()
        assert versions["merged"] is None
        refused = c.post("/sync/stop/files/answer", json={"path": DOC, "answer": "edited"})
        assert refused.json()["error"]["code"] == "SYNC_CONFLICT_MARKERS_LEFT"

        copy.write_text(MERGED)
        file = _file(c)
        assert file["agent_state"] == "merged_by_agent" and file["agent_merged_at"]
        assert file["answer"] is None, "an agent's merge is never an answer by itself"
        stopped = c.get("/sync/stop").json()["round"]
        assert stopped["unanswered"] == 1
        versions = c.get("/sync/stop/files/versions", params={"path": DOC}).json()
        assert versions["merged"] == MERGED
        assert "-Mini rotates on Fridays." in versions["merged_diff"]
        assert "+Both rotate" in versions["merged_diff"]

        resolved = c.post("/sync/stop/files/answer", json={"path": DOC, "answer": "edited"})
        assert resolved.json()["round"]["unanswered"] == 0
        assert c.post("/sync/continue").json()["status"] in ("pushed", "pulled_and_pushed")
    assert mini.disk(DOC) == MERGED.encode()


@pytest.mark.acceptance(
    spec="vault-sync", scenario="going back to two choices discards an agent's merge"
)
def test_going_back_to_two_choices_discards_the_merge(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    _conflict(mac, mini)
    with client_for(mini) as c:
        c.post("/sync/run")
        c.post("/sync/stop/handoff", json={})
        copy = Path(_file(c)["editor_path"])  # type: ignore[arg-type]
        copy.write_text(MERGED)
        assert _file(c)["agent_state"] == "merged_by_agent"
        c.post("/sync/stop/files/answer", json={"path": DOC, "answer": "edited"})

        back = c.post("/sync/stop/files/discard", json={"path": DOC}).json()["round"]
        file = back["files"][0]
        assert file["agent_state"] is None and file["answer"] is None
        assert file["editor_path"] is None and not copy.exists()
        assert back["unanswered"] == 1
        # The two choices still answer it, and an agent can be asked again.
        again = c.post("/sync/stop/handoff", json={}).json()
        assert again["paths"] == [DOC]
        assert _file(c)["agent_state"] == "handed_off"
        kept = c.post("/sync/stop/files/answer", json={"path": DOC, "answer": "mine"}).json()
        assert kept["round"]["unanswered"] == 0
        # Asking for a file's merge again after it was merged starts it over.
        c.post("/sync/stop/files/discard", json={"path": DOC})
        c.post("/sync/stop/handoff", json={})
        Path(_file(c)["editor_path"]).write_text(MERGED)  # type: ignore[arg-type]
        assert _file(c)["agent_state"] == "merged_by_agent"
        c.post("/sync/stop/handoff", json={"paths": [DOC]})
        assert _file(c)["agent_state"] == "handed_off"


def test_one_file_is_handed_over_alone(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    mac.put(DOC, "Mac rotates on Mondays.\n")
    mac.put(OTHER, "Mac: restart the worker first.\n")
    mac.round()
    mini.put(DOC, "Mini rotates on Fridays.\n")
    mini.put(OTHER, "Mini: page the owner first.\n")
    with client_for(mini) as c:
        assert c.post("/sync/run").json()["status"] == "stopped"
        got = c.post("/sync/stop/handoff", json={"paths": [OTHER]}).json()
        assert got["paths"] == [OTHER]
        assert OTHER in got["handoff"]["prompt"] and DOC not in got["handoff"]["prompt"]
        assert _file(c, OTHER)["agent_state"] == "handed_off"
        assert _file(c, DOC)["agent_state"] is None
        nothing = c.post("/sync/stop/handoff", json={"paths": ["knowledge/none.md"]})
        assert nothing.status_code == 409
        everything = c.post("/sync/stop/handoff", json={}).json()
        assert sorted(everything["paths"]) == sorted([DOC, OTHER])


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a join's differing files are handed to an agent too"
)
def test_a_joins_differing_files_share_the_conflict_shape(tmp_path: Path) -> None:
    mac, mini = fleet(tmp_path, "Mac", "Mini")
    mac.put(DOC, "Escalate after 15 min.\n")
    mac.run(mac.service.join())
    mini.put(DOC, "Escalate after 30 min.\n")
    mini.run(mini.service.join())
    with client_for(mini) as c:
        file = _file(c, join=True)
        assert file["reason"] == "join_differs" and file["agent_mergeable"] is True
        assert file["agent_state"] is None and file["secret"] is False

        got = c.post("/sync/join-choices/handoff", json={"agent": "Claude Code"}).json()
        prompt = got["handoff"]["prompt"]
        assert got["paths"] == [DOC] and DOC in prompt and "joined" in prompt
        copy = Path(c.post("/sync/join-choices/editor", json={"path": DOC}).json()["editor_path"])
        assert str(copy) in prompt and b"<<<<<<<" in copy.read_bytes()
        assert _file(c, join=True)["agent_state"] == "handed_off"

        refused = c.post(
            "/sync/join-choices", json={"choices": [{"path": DOC, "answer": "edited"}]}
        )
        assert refused.json()["error"]["code"] == "SYNC_CONFLICT_MARKERS_LEFT"
        copy.write_text("Escalate after 15 min; page the owner at 30.\n")
        assert _file(c, join=True)["agent_state"] == "merged_by_agent"
        versions = c.get("/sync/stop/files/versions", params={"path": DOC}).json()
        assert versions["merged"] == "Escalate after 15 min; page the owner at 30.\n"
        assert "+Escalate after 15 min; page the owner at 30." in versions["merged_diff"]

        done = c.post("/sync/join-choices", json={"choices": [{"path": DOC, "answer": "edited"}]})
        assert done.json() == {"files": []}
    assert mini.disk(DOC) == b"Escalate after 15 min; page the owner at 30.\n"
    # The merge is this machine's commit, so the next round pushes it.
    assert mini.round().status in (RoundStatus.PUSHED, RoundStatus.PULLED_AND_PUSHED)
    mac.round()
    assert mac.disk(DOC) == b"Escalate after 15 min; page the owner at 30.\n"


def test_a_join_file_goes_back_to_two_choices(tmp_path: Path) -> None:
    mac, mini = fleet(tmp_path, "Mac", "Mini")
    mac.put(DOC, "Escalate after 15 min.\n")
    mac.run(mac.service.join())
    mini.put(DOC, "Escalate after 30 min.\n")
    mini.run(mini.service.join())
    with client_for(mini) as c:
        c.post("/sync/join-choices/handoff", json={})
        copy = Path(_file(c, join=True)["editor_path"])  # type: ignore[arg-type]
        gone = c.post("/sync/join-choices/discard", json={"path": DOC}).json()
        assert gone["files"][0]["agent_state"] is None and not copy.exists()
        kept = c.post("/sync/join-choices", json={"choices": [{"path": DOC, "answer": "mine"}]})
        assert kept.json() == {"files": []}

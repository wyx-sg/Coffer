"""The chores sync hands to the person's agent (spec vault-sync "Hand
conflicting files to an agent", "Hand a remote's failure to an agent"): the
prompt a stopped round, a refused push and a missing git carry, and what it may
and may not contain. The merge itself is in ``test_agent_merge``."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from coffer.application.sync.attention import SyncAttentionSource
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundStatus
from coffer.domain.sync.stops import ConflictFile, ConflictReason

from .conftest import client_for
from .harness import Box, joined

DOC = "knowledge/team/on-call.md"
SECRET_FILE = "secret/sync-token.enc"


def _conflict(mac: Box, mini: Box) -> None:
    mac.put(DOC, "Mac rotates on Mondays.\n")
    mac.round()
    mini.put(DOC, "Mini rotates on Fridays.\n")


def _with_secret_conflict(box: Box) -> None:
    """Add an encrypted secret to the round ``box`` stopped on. A secret's
    ciphertext normally never conflicts (the fresher one wins), so the stop is
    extended by hand to prove the guard around one that does."""
    stop = box.state.stop()
    assert stop is not None
    blob = box.git.hash(b"gAAAA-ciphertext")
    secret = ConflictFile(
        path=SECRET_FILE,
        area="secret",
        reason=ConflictReason.BOTH_CHANGED,
        ours=blob,
        theirs=box.git.hash(b"gAAAA-other-ciphertext"),
        theirs_machine="Mac",
    )
    box.state.set_stop(dataclasses.replace(stop, conflicts=(*stop.conflicts, secret)))


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an encrypted secret in conflict offers only the two choices"
)
def test_a_secret_file_in_conflict_is_never_handed_to_an_agent(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    _conflict(mac, mini)
    assert mini.round().status is RoundStatus.STOPPED
    _with_secret_conflict(mini)
    with client_for(mini) as c:
        assert c.post("/sync/stop/files/answer", json={"path": DOC, "answer": "mine"}).is_success
        stopped = c.get("/sync/stop").json()["round"]
        (f,) = [f for f in stopped["files"] if f["path"] == SECRET_FILE]
        assert (f["secret"], f["agent_mergeable"]) == (True, False)
        editor = c.post("/sync/stop/files/editor", json={"path": SECRET_FILE})
        assert editor.json()["error"]["code"] == "SYNC_SECRET_NOT_EDITABLE"
        edited = c.post("/sync/stop/files/answer", json={"path": SECRET_FILE, "answer": "edited"})
        assert edited.json()["error"]["code"] == "SYNC_SECRET_NOT_EDITABLE"
        nothing = c.post("/sync/stop/handoff", json={})
        assert nothing.status_code == 409, "nothing left for an agent"
        by_path = c.post("/sync/stop/handoff", json={"paths": [SECRET_FILE]})
        assert by_path.json()["error"]["code"] == "SYNC_SECRET_NOT_EDITABLE"
        kept = c.post("/sync/stop/files/answer", json={"path": SECRET_FILE, "answer": "theirs"})
        assert kept.json()["round"]["unanswered"] == 0


def test_the_merge_prompt_counts_secret_files_without_their_contents(
    pair: tuple[Box, Box],
) -> None:
    mac, mini = pair
    _conflict(mac, mini)
    assert mini.round().status is RoundStatus.STOPPED
    _with_secret_conflict(mini)
    prompt = mini.run(mini.service.conflict_handoff())
    assert prompt is not None and DOC in prompt
    assert "1 encrypted secret file is in conflict too" in prompt
    assert "ciphertext" not in prompt and SECRET_FILE not in prompt
    items = mini.run(SyncAttentionSource(sync=mini.service).items())
    assert items[0].reason_code == "sync_conflicts" and items[0].handoff == prompt


def _reject_pushes(remote: str) -> None:
    hook = Path(remote) / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'protected branch hook declined' >&2\nexit 1\n")
    hook.chmod(0o755)


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a refused push carries a hand-off without a secret"
)
def test_a_refused_push_hands_its_diagnosis_to_an_agent(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    https = "https://oauth2:glpat-abcdefghijklmnop1234@gitlab.example/team/vault.git"
    _reject_pushes(mac.url)
    mac.put(DOC, "A change the remote refuses.\n")
    got = mac.round()
    assert got.status is RoundStatus.PUSH_FAILED
    # The status shows the remote the person set up; the prompt names it
    # without the credentials a URL may carry.
    mac.remotes.put(
        dataclasses.replace(
            mac.remotes.get() or SyncRemote(url=mac.url),
            url=https,
            secret_ref="sync/gitlab-token",
            username="oauth2",
        )
    )
    problem = mac.run(mac.service.status()).problem
    assert problem is not None and problem.kind == "push_failed"
    prompt = problem.handoff or ""
    assert "https://gitlab.example/team/vault.git" in prompt
    assert "Branch: main" in prompt and "declined" in prompt
    assert "sync/gitlab-token" in prompt and "glpat-" not in prompt
    assert "Retry" in prompt
    items = mac.run(SyncAttentionSource(sync=mac.service).items())
    (item,) = [i for i in items if i.reason_code == "sync_push_failed"]
    assert item.handoff == prompt
    with client_for(mac) as c:
        body = c.get("/sync/status").json()["problem"]
        assert body["kind"] == "push_failed" and body["handoff"]["prompt"] == prompt


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a machine without git is handed the install chore"
)
def test_git_missing_is_handed_to_an_agent(tmp_path: Path) -> None:
    (mac,) = joined(tmp_path, "Mac")
    mac.service._git_available = lambda: False
    problem = mac.run(mac.service.status()).problem
    assert problem is not None and problem.kind == "git_missing"
    prompt = problem.handoff or ""
    assert "install git" in prompt.lower() and "xcode-select" not in prompt

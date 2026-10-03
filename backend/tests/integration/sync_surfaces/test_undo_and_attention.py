"""Retiring a machine and stopping sync need no confirmation because each can
be undone (spec vault-sync "Undo a retired machine", "Undo stop syncing"), and
the attention items name the situation they are about, so ignoring one does not
hide the next (spec vault-sync "Say a vault needs a human where the user already is")."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from coffer.application.attention import attention_key
from coffer.application.sync.attention import SyncAttentionSource, fingerprint
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundRecord, RoundStatus
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.sync_dependencies import set_sync_service

from .conftest import TOKEN, client_for
from .harness import Box, bare_remote, joined

DOC = "knowledge/team/on-call.md"


@pytest.fixture(autouse=True)
def _token() -> Iterator[None]:
    set_active_token(TOKEN)
    yield
    set_active_token(None)
    set_sync_service(None)


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a retired machine is registered again with its descriptor"
)
def test_a_retired_machine_is_registered_again(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    mac.round()
    before = mac.disk("machines/mini.json")
    assert before is not None
    with client_for(mac) as c:
        assert c.delete("/sync/machines/mini").json() == {"removed": True}
        assert mac.disk("machines/mini.json") is None
        names = [m["machine_id"] for m in c.get("/sync/machines").json()["machines"]]
        assert "mini" not in names

        back = c.post("/sync/machines/mini/restore").json()
        assert back["machine_id"] == "mini" and back["is_self"] is False
        assert mac.disk("machines/mini.json") == before
        # Registering what is registered already changes nothing.
        assert c.post("/sync/machines/mini/restore").json()["machine_id"] == "mini"
        assert c.post("/sync/machines/nobody/restore").json()["error"]["code"] == (
            "SYNC_MACHINE_NOT_FOUND"
        )
        assert c.post("/sync/machines/mac/restore").status_code == 422
    # The restore is a commit like the retire, so the next round pushes it.
    assert mac.round().status in (RoundStatus.PUSHED, RoundStatus.PULLED_AND_PUSHED)


@pytest.mark.acceptance(spec="vault-sync", scenario="stopping sync can be undone")
def test_stopping_sync_is_undone_with_what_it_removed(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    mac.put(DOC, "Mac rotates on Mondays.\n")
    mac.round()
    mini.put(DOC, "Mini rotates on Fridays.\n")
    mini.round()  # stops on the conflict
    remote = SyncRemote(
        url=mini.url,
        interval_seconds=600,
        secret_ref="sync/token",
        username="oauth2",
        include_secret=True,
    )
    mini.remotes.put(remote)
    with client_for(mini) as c:
        assert c.post("/sync/remote/restore").json()["error"]["code"] == "SYNC_NOTHING_TO_RESTORE"
        assert c.delete("/sync/remote").json() == {"cleared": True, "restorable": True}
        assert mini.remotes.get() is None and mini.state.stop() is None
        # Nothing the client is told carries a secret: the ref is only a name.
        assert c.get("/sync/remote").json() == {"configured": False, "remote": None}

        back = c.post("/sync/remote/restore").json()
        assert back["url"] == remote.url and back["interval_seconds"] == 600
        assert back["secret_ref"] == "sync/token" and back["username"] == "oauth2"
        assert back["include_secret"] is True and back["enabled"] is True
        assert mini.remotes.get() == remote
        assert mini.state.joined(), "the machine is still joined"
        stopped = c.get("/sync/stop").json()
        assert stopped["stopped"] and stopped["round"]["unanswered"] == 1
        assert c.post("/sync/remote/restore").json()["error"]["code"] == "SYNC_NOTHING_TO_RESTORE"

        # Another remote set since: the old one is not put back over it.
        c.delete("/sync/remote")
        other = str(bare_remote(mini.root / "other"))
        c.put("/sync/remote", json={"url": other})
        assert c.post("/sync/remote/restore").json()["error"]["code"] == "SYNC_NOTHING_TO_RESTORE"


def test_restoring_over_a_remote_set_since_is_refused(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    with client_for(mac) as c:
        c.delete("/sync/remote")
        mac.remotes.put(SyncRemote(url=mac.url))
        refused = c.post("/sync/remote/restore")
        assert refused.status_code == 409 and refused.json()["error"]["code"] == (
            "SYNC_REMOTE_EXISTS"
        )


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an ignored item returns when the situation changes"
)
def test_an_attention_item_is_named_by_its_situation(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    mac.put(DOC, "Mac rotates on Mondays.\n")
    mac.round()
    mini.put(DOC, "Mini rotates on Fridays.\n")
    mini.round()

    def conflict_item() -> tuple[str, str | None]:
        items = mini.run(SyncAttentionSource(sync=mini.service).items())
        (item,) = [i for i in items if i.reason_code == "sync_conflicts"]
        return attention_key(item), item.uid

    key, uid = conflict_item()
    assert uid and conflict_item() == (key, uid), "the same situation keeps its key"
    stop = mini.state.stop()
    assert stop is not None
    extra = dataclasses.replace(stop.conflicts[0], path="knowledge/team/runbook.md")
    mini.state.set_stop(dataclasses.replace(stop, conflicts=(*stop.conflicts, extra)))
    assert conflict_item()[0] != key, "another set of files is another item"

    assert fingerprint("a", ["x", "y"]) == fingerprint("a", ["y", "x"])
    assert fingerprint("a", ["x"]) != fingerprint("a", ["x", "y"])


def test_git_missing_and_an_unreachable_remote_have_their_own_items(tmp_path: Path) -> None:
    (mac,) = joined(tmp_path, "Mac")
    mac.service._git_available = lambda: False
    items = mac.run(SyncAttentionSource(sync=mac.service).items())
    (item,) = [i for i in items if i.reason_code == "sync_git_missing"]
    assert item.handoff and "git" in item.handoff.lower()
    # Asking again after git is installed is just asking: the item is gone.
    mac.service._git_available = lambda: True
    assert not [
        i
        for i in mac.run(SyncAttentionSource(sync=mac.service).items())
        if i.reason_code == "sync_git_missing"
    ]

    later = datetime.now(tz=UTC) + timedelta(minutes=5)
    mac.run(
        mac.history.append(
            RoundRecord(
                status=RoundStatus.UNREACHABLE,
                started_at=later.isoformat(timespec="seconds"),
                finished_at=later.isoformat(timespec="seconds"),
                trigger="timer",
                detail="Could not resolve host: git.example",
            )
        )
    )
    items = mac.run(SyncAttentionSource(sync=mac.service).items())
    (down,) = [i for i in items if i.reason_code == "sync_unreachable"]
    assert down.uid and down.handoff
    again = mac.run(SyncAttentionSource(sync=mac.service).items())
    assert [attention_key(i) for i in again if i.reason_code == "sync_unreachable"] == [
        attention_key(down)
    ]

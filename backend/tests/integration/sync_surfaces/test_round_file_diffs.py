"""What a round changed in one file (spec vault-sync "Show what a round changed
in each file"): computed from the vault's history, for the files the round
lists, and never for a secret."""

from __future__ import annotations

import dataclasses

import pytest

from coffer.domain.sync.remote import SyncRemote

from .conftest import client_for
from .harness import Box

DOC = "knowledge/team/on-call.md"
OLD = "Primary on-call rotates every Monday.\n"
NEW = "Primary on-call rotates every Tuesday.\n"


@pytest.mark.acceptance(spec="vault-sync", scenario="an applied file shows its line-by-line diff")
def test_an_applied_file_shows_the_edit_that_came_in(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    mac.put(DOC, NEW)
    mac.round()
    pulled = mini.round()
    with client_for(mini) as c:
        got = c.get(f"/sync/runs/{pulled.id}/diff", params={"path": DOC, "side": "applied"})
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["kind"] == "text"
        assert f"-{OLD}" in body["diff"] and f"+{NEW}" in body["diff"]
        assert (body["added"], body["removed"]) == (1, 1)


@pytest.mark.acceptance(spec="vault-sync", scenario="a pushed file shows its line-by-line diff")
def test_a_pushed_file_is_against_what_the_remote_held(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    mac.put(DOC, NEW)
    pushed = mac.round()
    with client_for(mac) as c:
        got = c.get(f"/sync/runs/{pushed.id}/diff", params={"path": DOC, "side": "pushed"})
        assert got.status_code == 200, got.text
        assert f"-{OLD}" in got.json()["diff"] and f"+{NEW}" in got.json()["diff"]

    # A round that pulled and pushed compares with the tip it pushed on top of.
    mini.put("knowledge/team/mini.md", "from the mini\n")
    mac.put(DOC, NEW + "second line\n")
    mac.round()
    both = mini.round()
    assert both.applied and both.pushed
    with client_for(mini) as c:
        got = c.get(
            f"/sync/runs/{both.id}/diff",
            params={"path": "knowledge/team/mini.md", "side": "pushed"},
        )
        assert got.status_code == 200, got.text
        assert got.json()["diff"].count("+from the mini") == 1


@pytest.mark.acceptance(spec="vault-sync", scenario="a secret file shows no content")
def test_a_secret_file_carries_no_content(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    remote = mac.remotes.get() or SyncRemote(url=mac.url)
    mac.remotes.put(dataclasses.replace(remote, include_secret=True))
    mac.put("secret/orders-db.enc", "gAAAAciphertext\n")
    pushed = mac.round()
    with client_for(mac) as c:
        got = c.get(
            f"/sync/runs/{pushed.id}/diff",
            params={"path": "secret/orders-db.enc", "side": "pushed"},
        )
        assert got.status_code == 200, got.text
        assert got.json()["kind"] == "secret"
        assert got.json()["diff"] is None
        assert "ciphertext" not in got.text


@pytest.mark.acceptance(spec="vault-sync", scenario="a path the round did not touch is refused")
def test_a_path_the_round_did_not_list_is_refused(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    mac.put(DOC, NEW)
    pushed = mac.round()
    with client_for(mac) as c:
        for path, side in ((DOC, "applied"), ("knowledge/other.md", "pushed"), ("../x", "pushed")):
            got = c.get(f"/sync/runs/{pushed.id}/diff", params={"path": path, "side": side})
            assert got.status_code == 404, got.text
            assert got.json()["error"]["code"] == "SYNC_ROUND_FILE_NOT_LISTED"


def test_a_binary_file_has_no_line_diff_and_gone_commits_are_unavailable(
    pair: tuple[Box, Box],
) -> None:
    mac, _mini = pair
    mac.put("knowledge/team/blob.bin", b"\x00\x01\x02\xff")
    pushed = mac.round()
    with client_for(mac) as c:
        got = c.get(
            f"/sync/runs/{pushed.id}/diff",
            params={"path": "knowledge/team/blob.bin", "side": "pushed"},
        )
        assert got.json()["kind"] == "binary" and got.json()["diff"] is None
        i = next(n for n, r in enumerate(mac.history.rows) if r.id == pushed.id)
        mac.history.rows[i] = dataclasses.replace(mac.history.rows[i], to_commit="0" * 40)
        gone = c.get(
            f"/sync/runs/{pushed.id}/diff",
            params={"path": "knowledge/team/blob.bin", "side": "pushed"},
        )
        assert gone.status_code == 409
        assert gone.json()["error"]["code"] == "SYNC_ROUND_DIFF_UNAVAILABLE"

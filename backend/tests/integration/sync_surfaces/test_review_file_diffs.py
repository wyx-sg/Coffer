"""What a person reviews before acting (spec vault-sync "Review a file's change
before acting on it"): a file waiting to push, as one change from the remote's
tip, and a file a held round would delete, as its whole text removed — each
only for a path that list names."""

from __future__ import annotations

import pytest

from .conftest import client_for
from .harness import Box

DOC = "knowledge/team/on-call.md"
OLD = "Primary on-call rotates every Monday.\n"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a waiting file shows its change since the last push"
)
def test_a_waiting_file_is_one_change_across_its_commits(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    mac.put(DOC, "Primary on-call rotates every Tuesday.\n")
    mac.put(DOC, "Primary on-call rotates every Wednesday.\n")
    with client_for(mac) as c:
        got = c.get("/sync/pending/diff", params={"path": DOC})
        assert got.status_code == 200, got.text
        body = got.json()
        assert (body["side"], body["kind"]) == ("pending", "text")
        assert f"-{OLD}" in body["diff"]
        assert "+Primary on-call rotates every Wednesday." in body["diff"]
        assert "Tuesday" not in body["diff"]
        assert (body["added"], body["removed"]) == (1, 1)

        other = c.get("/sync/pending/diff", params={"path": "knowledge/other.md"})
        assert other.status_code == 404
        assert other.json()["error"]["code"] == "SYNC_ROUND_FILE_NOT_LISTED"


def _bulk(n: int) -> list[str]:
    return [f"knowledge/bulk/note-{i:02}.md" for i in range(n)]


@pytest.mark.acceptance(spec="vault-sync", scenario="a held file shows the text a delete removes")
def test_a_held_file_shows_its_whole_text_removed_both_ways(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    for path in _bulk(25):
        mac.put(path, f"{path}\nsecond line\n")
    mac.round()
    mini.round()
    mac.remove(*_bulk(25))

    assert mac.round().status.value == "held"
    first = _bulk(25)[0]
    with client_for(mac) as c:
        got = c.get("/sync/hold/diff", params={"path": first})
        assert got.status_code == 200, got.text
        body = got.json()
        assert (body["side"], body["kind"]) == ("held", "text")
        assert (body["added"], body["removed"]) == (0, 2)
        assert f"-{first}" in body["diff"]
        missing = c.get("/sync/hold/diff", params={"path": DOC})
        assert missing.status_code == 404

    mac.run(mac.service.confirm_hold())
    mac.run(mac.service.continue_round())
    assert mini.round().status.value == "held"
    with client_for(mini) as c:
        got = c.get("/sync/hold/diff", params={"path": first})
        assert got.status_code == 200, got.text
        assert got.json()["removed"] == 2 and got.json()["added"] == 0


def test_nothing_held_refuses_a_held_diff(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    with client_for(mac) as c:
        got = c.get("/sync/hold/diff", params={"path": DOC})
        assert got.status_code == 404
        assert got.json()["error"]["code"] == "SYNC_ROUND_FILE_NOT_LISTED"

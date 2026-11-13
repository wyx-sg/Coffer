"""What a person reviews before acting (spec vault-sync "Review a file's change
before acting on it"): a file waiting to push, as one change from the remote's
tip, only for a path that list names."""

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

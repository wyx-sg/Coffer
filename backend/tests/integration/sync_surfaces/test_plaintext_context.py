"""A plaintext finding shown in its file (spec vault-sync "Show a plaintext
finding in its file"): the lines around it with every value masked and its
shape in its place, whether the remote holds the file and the line, and a
modified file's masked change — never the value."""

from __future__ import annotations

import random
import string

import pytest

from coffer.domain.sync.rounds import RoundStatus

from .conftest import client_for
from .harness import Box

DOC = "knowledge/team/db.md"
#: Built at run time so no secret-shaped literal sits in the source.
_RNG = random.Random(20261005)
_LOWER_DIGIT = string.ascii_lowercase + string.digits
VALUE = "q7" + "".join(_RNG.choices(_LOWER_DIGIT, k=16))
OTHER = "k3" + "".join(_RNG.choices(_LOWER_DIGIT, k=18))
TOKEN = "ghp_" + "".join(_RNG.choices(string.ascii_letters + string.digits, k=36))


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a finding is shown in its file with the value masked"
)
def test_a_new_files_finding_is_shown_masked_with_its_shape(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    with client_for(mac) as c:
        early = c.get("/sync/plaintext/context", params={"path": DOC, "line": 4})
        assert early.status_code == 409
        assert early.json()["error"]["code"] == "SYNC_NO_PLAINTEXT_FOUND"

        mac.put(
            DOC,
            "# Orders database\n\nHost: db.internal\n"
            f"DB_PASSWORD={VALUE}\nAPI_TOKEN={OTHER}\nnote: rotate monthly\n"
            "tail 1\ntail 2\n",
        )
        assert mac.round().status is RoundStatus.PLAINTEXT_FOUND
        got = c.get("/sync/plaintext/context", params={"path": DOC, "line": 4})
        assert got.status_code == 200, got.text
        body = got.json()
        assert VALUE not in got.text and OTHER not in got.text

        assert (body["path"], body["line"], body["key"]) == (DOC, 4, "DB_PASSWORD")
        assert body["change"] == "added" and body["on_remote"] is False
        assert body["diff"] is None
        assert [r["number"] for r in body["lines"]] == [1, 2, 3, 4, 5, 6, 7]
        flagged = body["lines"][3]
        assert flagged["text"] == "DB_PASSWORD=" + "•" * len(VALUE)
        (value,) = flagged["values"]
        assert (value["start"], value["end"], value["key"]) == (12, 12 + len(VALUE), "DB_PASSWORD")
        assert value["rule"] == "coffer-password-assignment"
        assert value["shape"] == {
            "length": len(VALUE),
            "classes": ["lower", "digit"],
            "prefix": None,
            "hint": None,
            "word": None,
        }
        # A neighbouring value is masked as well; plain lines read as they are.
        assert body["lines"][4]["text"] == "API_TOKEN=" + "•" * len(OTHER)
        assert body["lines"][2]["text"] == "Host: db.internal"

        missing = c.get("/sync/plaintext/context", params={"path": DOC, "line": 3})
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "SYNC_PLAINTEXT_NOT_LISTED"


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a finding in a file the remote holds shows its masked change",
)
def test_a_modified_files_finding_shows_its_masked_change(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    mac.put(DOC, "# Orders database\n\nDB_PASSWORD=my-demo-pass-2024\n")
    first = mac.round()
    assert first.status is RoundStatus.PLAINTEXT_FOUND
    # The person checks it is a demo value, and pushes it anyway.
    assert mac.run(mac.service.push_anyway(actor="user")).status is RoundStatus.PUSHED
    mac.put(
        DOC,
        f"# Orders database\n\nDB_PASSWORD=my-demo-pass-2024\ntoken: {TOKEN}\n",
    )
    assert mac.round().status is RoundStatus.PLAINTEXT_FOUND
    with client_for(mac) as c:
        # Push anyway remembered the demo value, so only the token is listed.
        old = c.get("/sync/plaintext/context", params={"path": DOC, "line": 3})
        assert old.json()["error"]["code"] == "SYNC_PLAINTEXT_NOT_LISTED"

        new = c.get("/sync/plaintext/context", params={"path": DOC, "line": 4})
        assert TOKEN not in new.text and "demo-pass" not in new.text
        body = new.json()
        assert body["change"] == "modified" and body["on_remote"] is False
        (example,) = body["lines"][2]["values"]
        assert (example["shape"]["hint"], example["shape"]["word"]) == ("placeholder", "demo")
        (tok,) = body["lines"][3]["values"]
        assert (tok["key"], tok["rule"]) == ("token", "github-pat")
        assert tok["shape"]["prefix"] == "ghp_"
        assert body["lines"][3]["text"] == "token: ghp_" + "•" * (len(TOKEN) - 4)
        assert (body["added"], body["removed"]) == (1, 0)
        assert "+token: ghp_" + "•" * (len(TOKEN) - 4) in body["diff"]

"""A round never pushes a plaintext secret (spec vault-sync "Refuse to push a
plaintext secret"): it stops before pushing and names the file, line and key;
a value removed since is folded out of the unpushed history; "Push anyway"
allows exactly what was found and is audited; ciphertext is not read."""

from __future__ import annotations

import dataclasses
import json
import random
import string
import subprocess
from pathlib import Path
from typing import Any

import pytest

from coffer.application.sync.attention import SyncAttentionSource
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundStatus

from ..sync_thin.machines import resource
from .conftest import client_for
from .harness import Box

DOC = "knowledge/team/db.md"
#: Built at run time so no secret-shaped literal sits in the source.
VALUE = "q7" * 8
_RNG = random.Random(20261005)
TOKEN = "ghp_" + "".join(_RNG.choices(string.ascii_letters + string.digits, k=36))
#: A Stripe secret key, put together at run time: no vendor-shaped literal.
STRIPE = "sk_" + "live_" + "".join(_RNG.choices(string.ascii_letters + string.digits, k=28))


def _remote_objects(url: str) -> bytes:
    """Every object the bare remote holds, concatenated."""
    done = subprocess.run(
        ["git", "-C", url, "cat-file", "--batch-all-objects", "--batch"],
        capture_output=True,
        check=True,
    )
    return done.stdout


def _leak(mac: Box) -> None:
    mac.put(DOC, f"# Orders database\n\nHost: db.internal\nDB_PASSWORD={VALUE}\n")


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a plaintext secret stops the round before anything is pushed"
)
def test_a_plaintext_secret_stops_the_round_and_is_named_without_its_value(
    pair: tuple[Box, Box],
) -> None:
    mac, mini = pair
    before = mac.git.fetch("main", None)
    _leak(mac)
    got = mac.round()
    assert got.status is RoundStatus.PLAINTEXT_FOUND
    (found,) = got.plaintext
    assert (found.path, found.line, found.key, found.rule, found.current) == (
        DOC,
        4,
        "DB_PASSWORD",
        "coffer-password-assignment",
        True,
    )
    assert mac.git.fetch("main", None) == before, "nothing was pushed"
    assert VALUE.encode() not in _remote_objects(mac.url)
    assert VALUE not in str(got.to_json())

    problem = mac.run(mac.service.status()).problem
    assert problem is not None and problem.kind == "plaintext_found"
    # A plaintext secret is never handed to an agent: no surface carries a prompt.
    assert problem.handoff is None and VALUE not in problem.message
    items = mac.run(SyncAttentionSource(sync=mac.service).items())
    (item,) = [i for i in items if i.reason_code == "sync_plaintext_found"]
    assert f"{DOC}:4" in item.reason and item.handoff is None
    assert "Move it into secrets, or push anyway" in item.reason
    with client_for(mac) as c:
        body = c.get("/sync/status").json()["problem"]
        assert body["kind"] == "plaintext_found" and body["handoff"] is None
        assert body["plaintext"] == [
            {
                "path": DOC,
                "line": 4,
                "key": "DB_PASSWORD",
                "rule": "coffer-password-assignment",
                "current": True,
            }
        ]
    mini.round()
    assert mini.disk(DOC) is None, "the other machine never received it"


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a value removed before the push is not published from the history",
)
def test_a_fixed_file_is_pushed_with_its_unpushed_commits_folded(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    _leak(mac)
    assert mac.round().status is RoundStatus.PLAINTEXT_FOUND
    mac.put(DOC, "# Orders database\n\nHost: db.internal\nDB_PASSWORD=coffer://secret/orders-db\n")
    mac.put("knowledge/team/deploy.md", "Deploy on Tuesdays.\n")
    got = mac.round()
    assert got.status is RoundStatus.PUSHED and got.folded >= 3
    assert not got.plaintext
    assert VALUE.encode() not in _remote_objects(mac.url)
    assert mac.git.head() == mac.git.fetch("main", None)
    # The descriptor in what was pushed names a commit the remote holds.
    descriptor = json.loads(mac.disk(mac.host.descriptor_path()) or b"{}")
    known = subprocess.run(
        ["git", "--git-dir", mac.url, "cat-file", "-e", descriptor["last_converged_commit"]],
        capture_output=True,
    )
    assert known.returncode == 0
    mini.round()
    assert mini.disk(DOC) == mac.disk(DOC)
    assert mini.disk("knowledge/team/deploy.md") == b"Deploy on Tuesdays.\n"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="push anyway allows exactly what was found and is audited"
)
def test_push_anyway_pushes_the_found_versions_and_records_it(pair: tuple[Box, Box]) -> None:
    mac, mini = pair
    with client_for(mac) as c:
        refused = c.post("/sync/plaintext/push-anyway")
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "SYNC_NO_PLAINTEXT_FOUND"
        _leak(mac)
        assert c.post("/sync/run").json()["status"] == "plaintext_found"
        pushed = c.post("/sync/plaintext/push-anyway").json()
        assert pushed["status"] == "pushed"
    (event,) = [e for e in mac.audit.events if e[0] == "sync_plaintext_pushed"]
    assert event[1]["actor"] == "user" and event[1]["details"]["files"] == [f"{DOC}:4"]
    mini.round()
    assert mini.disk(DOC) == mac.disk(DOC)
    # A new value in the same file is a new version, read again.
    mac.put(DOC, f"token: {TOKEN}\n")
    again = mac.round()
    assert again.status is RoundStatus.PLAINTEXT_FOUND
    assert [(f.line, f.key) for f in again.plaintext] == [(1, "token")]


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a value pushed anyway does not stop a later edit of its file"
)
def test_a_value_pushed_anyway_does_not_stop_a_later_edit_of_its_file(
    pair: tuple[Box, Box],
) -> None:
    mac, _mini = pair
    with client_for(mac) as c:
        _leak(mac)
        assert c.post("/sync/run").json()["status"] == "plaintext_found"
        status = c.get("/sync/status").text
        assert "fingerprint" not in status
        assert "fingerprint" not in c.post("/sync/run").text
        pushed = c.post("/sync/plaintext/push-anyway")
        assert pushed.json()["status"] == "pushed" and "fingerprint" not in pushed.text
    mac.put(DOC, f"# Orders database\n\nHost: db.other\nDB_PASSWORD={VALUE}\n")
    assert mac.round().status is RoundStatus.PUSHED
    mac.put(DOC, f"# Orders database\n\nHost: db.other\nDB_PASSWORD={VALUE}x\n")
    again = mac.round()
    assert again.status is RoundStatus.PLAINTEXT_FOUND
    assert [(f.line, f.key) for f in again.plaintext] == [(4, "DB_PASSWORD")]


@pytest.mark.acceptance(spec="vault-sync", scenario="an encrypted secret file is not read")
def test_ciphertext_is_not_read_as_plaintext(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    remote = mac.remotes.get() or SyncRemote(url=mac.url)
    mac.remotes.put(dataclasses.replace(remote, include_secret=True))
    mac.put("secret/orders-db.enc", f"gAAAA{TOKEN}\n")
    got = mac.round()
    assert got.status is RoundStatus.PUSHED, got.detail
    assert "secret/orders-db.enc" in {c.path for c in got.pushed}


def test_the_detection_runs_over_every_unpushed_version(tmp_path: Path) -> None:
    """Unit-sized: a blob that is only in history is reported as not current."""
    from coffer.application.sync import round_plaintext

    from .harness import joined

    (mac,) = joined(tmp_path, "Mac")
    tip = mac.git.fetch("main", None)
    _leak(mac)
    mac.put(DOC, "fixed\n")
    head = mac.git.head()
    assert head is not None
    (found,) = round_plaintext.findings(mac.deps, tip, head)
    assert found.current is False and found.key == "DB_PASSWORD"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a vendor token in a knowledge note stops the round"
)
def test_a_vendor_token_in_prose_stops_the_round(pair: tuple[Box, Box]) -> None:
    mac, _mini = pair
    before = mac.git.fetch("main", None)
    mac.put(DOC, f"# Billing\n\nWe charge cards with {STRIPE} from the dashboard.\n")
    got = mac.round()
    assert got.status is RoundStatus.PLAINTEXT_FOUND
    (found,) = got.plaintext
    assert (found.path, found.line, found.rule) == (DOC, 3, "stripe-access-token")
    assert found.key == "stripe-access-token"
    assert mac.git.fetch("main", None) == before, "nothing was pushed"
    assert STRIPE.encode() not in _remote_objects(mac.url)


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a resource document's secret references do not stop a push",
)
def test_secret_references_in_a_resource_document_do_not_stop_a_push(
    pair: tuple[Box, Box],
) -> None:
    mac, _mini = pair
    refs = {
        "Authorization": "secret/" + "".join(_RNG.choices("0123456789abcdef", k=32)),
        "X-Api-Key": "secret/" + "".join(_RNG.choices("0123456789abcdef", k=32)),
    }
    config: dict[str, Any] = {
        "transport": {"type": "http", "url": "https://mcp.example.test", "secret_refs": refs}
    }
    mac.put(
        "resources/mcp_server/billing.json",
        resource("mcp_server", "billing", "a" * 32, config),
    )
    got = mac.round()
    assert got.status is RoundStatus.PUSHED, got.detail
    assert "resources/mcp_server/billing.json" in {c.path for c in got.pushed}

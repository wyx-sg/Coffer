"""HTTP contract tests for /api/v1/sync (spec vault-sync ``## Surfaces``).

Every route is driven against a **real** :class:`ConvergeService` built by
``tests/integration/sync/harness.py``: two whole vaults, two SQLite databases,
two master keys and one real bare git repository between them. Nothing below
the git binary is faked, so a route that reports ``applied``/``published``
counts or a commit is reporting what git actually did, and a route with a side
effect can be checked against the vault and against the remote's tree.

Nothing here may reach the developer's real ``~/.coffer``: the harness pins
every root under ``tmp_path`` and injects the machine id, and the two roots the
production code would otherwise read from the environment are pinned as well.

There is no ``/export`` or ``/import`` any more (spec ``## Out of scope``);
that they are gone is asserted, and nothing else in this file mentions them.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.domain.scope import Scope
from coffer.domain.sync.backup import (
    DEFAULT_BRANCH,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_WORKTREE,
)
from coffer.domain.sync.manifest import SCHEMA_VERSION
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.sync_routes import (
    router as sync_router,
)
from coffer.surfaces.http.sync_routes import (
    set_machine_registry,
    set_sync_service,
)
from tests.integration.sync.harness import (
    MACHINE_A,
    MACHINE_B,
    VaultMachine,
    another_coffer_pushes,
    two_machines,
)

pytestmark = pytest.mark.timeout(180)

_TOKEN = "test-token-sync-http"

#: Five notes: the deletion guard's default share is 20%, so removing one of
#: five is exactly at the threshold rather than over it. Scenarios that are not
#: about the guard seed this many so an ordinary deletion can travel.
_ROOMY = 5


@pytest.fixture
async def fleet(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Two whole vaults, ``a`` being the one the routes are wired to."""
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "pinned-knowledge"))
    monkeypatch.setenv("COFFER_SKILLS_ROOT", str(tmp_path / "pinned-skills"))
    a, b = await two_machines(tmp_path)
    try:
        yield a, b
    finally:
        await a.close()
        await b.close()


@pytest.fixture
async def client(fleet):
    """A minimal app carrying only the sync router, over machine ``a``."""
    a, _b = fleet
    set_sync_service(a.service())
    set_machine_registry(a.registry)
    app = FastAPI()
    app.include_router(sync_router)
    err_handlers.register(app)
    set_active_token(_TOKEN)
    async with AsyncClient(
        transport=ASGITransport(app),
        base_url="http://t",
        headers={"X-Coffer-Token": _TOKEN},
    ) as c:
        yield c
    set_active_token(None)


async def _configure(client: AsyncClient, machine: VaultMachine) -> None:
    r = await client.put("/api/v1/sync/remote", json={"url": machine.remote_url})
    assert r.status_code == 200, r.text


def _code(response) -> str:  # type: ignore[no-untyped-def]
    return str(response.json()["error"]["code"])


# --- the remote -------------------------------------------------------------


async def test_remote_on_a_fresh_vault_is_unconfigured_not_an_error(client) -> None:
    """Sync being off is the ordinary state, so it is a 200 with a flag."""
    r = await client.get("/api/v1/sync/remote")

    assert r.status_code == 200
    assert r.json() == {"configured": False, "remote": None}


async def test_put_remote_with_a_bare_url_fills_in_the_spec_defaults(client, fleet) -> None:
    a, _b = fleet

    r = await client.put("/api/v1/sync/remote", json={"url": a.remote_url})

    assert r.status_code == 200
    assert r.json() == {
        "url": a.remote_url,
        "branch": DEFAULT_BRANCH,
        "credential_ref": None,
        "include_credentials": False,
        "interval_seconds": DEFAULT_INTERVAL_SECONDS,
        "enabled": True,
        "worktree_path": DEFAULT_WORKTREE,
    }
    stored = (await client.get("/api/v1/sync/remote")).json()
    assert stored["configured"] is True
    assert stored["remote"]["url"] == a.remote_url


async def test_put_remote_that_cannot_be_reached_is_rejected_at_the_front_door(
    client, tmp_path
) -> None:
    """The user is here now with the URL in front of them — the only cheap moment."""
    r = await client.put("/api/v1/sync/remote", json={"url": str(tmp_path / "no-such.git")})

    assert r.status_code == 422
    assert _code(r) == "BACKUP_REMOTE_INVALID"
    assert (await client.get("/api/v1/sync/remote")).json()["configured"] is False


@pytest.mark.parametrize(
    "body",
    [
        {"url": "-x"},
        {"url": "--receive-pack=touch pwned"},
        {"url": "https://example.invalid/v.git", "branch": "--receive-pack=x"},
        {"url": "https://example.invalid/v.git", "branch": "-x"},
        {"url": "https://example.invalid/v.git", "branch": "a..b"},
        {"url": "https://example.invalid/v.git", "branch": "a.lock"},
        {"url": "https://example.invalid/v.git", "branch": "with space"},
        {"url": "https://example.invalid/v.git", "worktree_path": ""},
    ],
)
async def test_put_remote_refuses_what_git_would_read_as_an_option(client, body) -> None:
    """The URL and the branch become git arguments. A value git would parse as
    an option — ``--receive-pack=<cmd>`` is a command — is a 422 at the wire,
    before any adapter sees it, and nothing is stored."""
    r = await client.put("/api/v1/sync/remote", json=body)

    assert r.status_code == 422, r.text
    assert (await client.get("/api/v1/sync/remote")).json()["configured"] is False


@pytest.mark.parametrize(
    "where",
    ["knowledge_root", "skills_root", "root", "relative"],
)
async def test_put_remote_refuses_a_working_tree_inside_the_vault(client, fleet, where) -> None:
    """spec vault-sync ``## Concepts`` (working tree): the round mirrors the
    vault *into* the tree and ``reset --hard``s it, so a tree at, inside or
    above a vault directory would copy the vault into itself and then erase
    it. Coffer's own directory is refused the same way, and so is a relative
    path, which would resolve against whatever the daemon's cwd happens to be."""
    a, _b = fleet
    set_sync_service(a.service(guard_worktree=True))
    path = "relative/sync" if where == "relative" else str(getattr(a, where))

    r = await client.put("/api/v1/sync/remote", json={"url": a.remote_url, "worktree_path": path})

    assert r.status_code == 422, r.text
    assert _code(r) == "BACKUP_REMOTE_INVALID"
    assert (await client.get("/api/v1/sync/remote")).json()["configured"] is False


async def test_put_remote_accepts_the_working_tree_beside_the_vault(client, fleet) -> None:
    a, _b = fleet
    set_sync_service(a.service(guard_worktree=True))

    r = await client.put(
        "/api/v1/sync/remote", json={"url": a.remote_url, "worktree_path": str(a.worktree)}
    )

    assert r.status_code == 200, r.text
    assert r.json()["worktree_path"] == str(a.worktree)


async def test_delete_remote_is_idempotent(client, fleet) -> None:
    a, _b = fleet
    await _configure(client, a)

    first = await client.delete("/api/v1/sync/remote")
    second = await client.delete("/api/v1/sync/remote")

    assert first.status_code == 200
    assert first.json() == {"cleared": True}
    assert second.status_code == 200
    assert second.json() == {"cleared": False}
    assert (await client.get("/api/v1/sync/remote")).json()["configured"] is False


# --- rounds -----------------------------------------------------------------


async def test_run_publishes_the_vault_to_a_real_remote(client, fleet) -> None:
    a, _b = fleet
    a.write_knowledge("notes", "one", "first note\n")
    await a.register("mcp_server", "files")
    await _configure(client, a)

    r = await client.post("/api/v1/sync/run", json={})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # The counts, field by field: the diff also carries the paths behind them
    # now, and a whole-object compare would break on every field added to it.
    assert [body["applied"][k] for k in ("added", "modified", "deleted")] == [0, 0, 0]
    assert body["applied"]["changes"] == []
    assert body["published"]["added"] >= 2  # the note and the resource
    assert body["published"]["deleted"] == 0
    # …and names them, which is what the history row's tally raises.
    assert any(c["path"].startswith("resources/") for c in body["published"]["changes"])
    assert body["commit"] is not None
    # The round reports the commit it reached; git resolves it to the branch tip.
    assert await a.mirror.resolve_revision(body["commit"]) == await a.mirror.head()
    assert await a.remote_commit_count() == 1
    assert body["conflicts"] == []
    assert body["failures"] == []
    assert body["pending"] is None

    remote = await a.remote_paths()
    assert "knowledge/notes/one.md" in remote
    assert f"machines/{MACHINE_A}.yaml" in remote
    assert await a.remote_text("knowledge/notes/one.md") == "first note\n"


async def test_run_without_a_remote_is_a_disabled_round(client) -> None:
    r = await client.post("/api/v1/sync/run", json={})

    assert r.status_code == 200
    assert r.json()["status"] == "disabled"
    assert r.json()["commit"] is None


async def test_adopt_joins_as_new_when_the_registry_has_never_seen_this_machine(
    client, fleet
) -> None:
    a, b = fleet
    b.write_knowledge("notes", "from-b", "written on the desktop\n")
    await b.converge()
    await b.converge()
    a.write_knowledge("notes", "from-a", "written on the laptop\n")
    await _configure(client, a)

    r = await client.post("/api/v1/sync/adopt", json={})

    assert r.status_code == 200
    body = r.json()
    assert body["join"] == "new"
    assert body["status"] == "ok"
    # A new machine takes the union: it gains B's note and loses none of its own.
    assert body["applied"]["deleted"] == 0
    assert body["published"]["deleted"] == 0
    assert a.read_knowledge("notes", "from-b") == "written on the desktop\n"
    assert a.read_knowledge("notes", "from-a") == "written on the laptop\n"
    assert {"knowledge/notes/from-a.md", "knowledge/notes/from-b.md"} <= await a.remote_paths()


async def test_adopt_needs_a_choice_when_a_returning_machine_has_lost_its_base(
    client, fleet
) -> None:
    """A first round publishes a descriptor naming no commit; a reinstall on
    that same day leaves the base unrecoverable, and neither default is safe."""
    a, _b = fleet
    a.write_knowledge("notes", "one", "first note\n")
    await _configure(client, a)
    assert (await client.post("/api/v1/sync/run", json={})).json()["status"] == "ok"
    a.state.forget()  # what a reinstall does to the machine-local pointer

    refused = await client.post("/api/v1/sync/adopt", json={})

    assert refused.status_code == 200
    assert refused.json()["status"] == "failed"
    assert "cannot be recovered" in (refused.json()["error"] or "")
    assert refused.json()["join"] is None

    chosen = await client.post("/api/v1/sync/adopt", json={"choice": "keep-local"})

    assert chosen.status_code == 200
    assert chosen.json()["join"] == "new"
    assert chosen.json()["status"] in {"ok", "no_change"}
    assert a.read_knowledge("notes", "one") == "first note\n"


# --- the deletion guard -----------------------------------------------------


async def _held_publish_round(client: AsyncClient, a: VaultMachine) -> dict:
    """Seed one note, publish it, delete it — the guard holds the deletion."""
    a.write_knowledge("notes", "only", "the only note\n")
    await _configure(client, a)
    assert (await client.post("/api/v1/sync/run", json={})).json()["status"] == "ok"
    a.delete_knowledge("notes", "only")

    r = await client.post("/api/v1/sync/run", json={})
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "awaiting_confirmation", body
    return body


async def test_a_round_that_would_delete_a_whole_area_is_held(client, fleet) -> None:
    a, _b = fleet

    body = await _held_publish_round(client, a)

    pending = body["pending"]
    assert pending["direction"] == "publish"
    assert pending["breaches"] == [{"area": "knowledge", "deleted": 1, "total": 1}]
    assert pending["paths"] == ["knowledge/notes/only.md"]
    assert pending["raised_at"]
    # Held means held: the remote still has the document.
    assert "knowledge/notes/only.md" in await a.remote_paths()


async def test_confirm_lets_a_held_round_finish(client, fleet) -> None:
    a, _b = fleet
    await _held_publish_round(client, a)

    r = await client.post("/api/v1/sync/confirm", json={})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok", body
    assert body["published"]["deleted"] == 1
    assert body["pending"] is None
    assert "knowledge/notes/only.md" not in await a.remote_paths()
    assert await a.state.pending() is None


async def test_reject_discards_a_held_round_and_the_remote_keeps_the_document(
    client, fleet
) -> None:
    a, _b = fleet
    await _held_publish_round(client, a)

    r = await client.post("/api/v1/sync/reject", json={})

    assert r.status_code == 200
    assert r.json() == {"cleared": True}
    assert "knowledge/notes/only.md" in await a.remote_paths()
    assert await a.state.pending() is None


async def test_confirm_with_nothing_held_is_409(client) -> None:
    r = await client.post("/api/v1/sync/confirm", json={})

    assert r.status_code == 409
    assert _code(r) == "SYNC_NOTHING_PENDING"


async def test_reject_with_nothing_held_is_409(client) -> None:
    r = await client.post("/api/v1/sync/reject", json={})

    assert r.status_code == 409
    assert _code(r) == "SYNC_NOTHING_PENDING"


# --- undoing ----------------------------------------------------------------


async def test_rollback_with_no_snapshot_is_409(client) -> None:
    r = await client.post("/api/v1/sync/rollback", json={})

    assert r.status_code == 409
    assert _code(r) == "SYNC_NOTHING_TO_ROLL_BACK"


async def test_rollback_undoes_the_last_applied_round(client, fleet) -> None:
    a, b = fleet
    for i in range(_ROOMY):
        a.write_knowledge("notes", f"n{i}", f"original {i}\n")
    await _configure(client, a)
    assert (await client.post("/api/v1/sync/run", json={})).json()["status"] == "ok"
    await b.converge()
    await b.converge()

    b.write_knowledge("notes", "n0", "rewritten by B\n")
    b.write_knowledge("notes", "extra", "new from B\n")
    await b.converge()
    applied = await client.post("/api/v1/sync/run", json={})
    assert applied.json()["status"] == "ok", applied.json()
    assert a.read_knowledge("notes", "n0") == "rewritten by B\n"
    assert a.read_knowledge("notes", "extra") == "new from B\n"

    r = await client.post("/api/v1/sync/rollback", json={})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["applied"]["deleted"] == 1  # "extra" goes back to not existing
    assert a.read_knowledge("notes", "n0") == "original 0\n"
    assert a.read_knowledge("notes", "extra") is None


async def test_restore_brings_back_a_deleted_document(client, fleet) -> None:
    a, _b = fleet
    for i in range(_ROOMY):
        a.write_knowledge("notes", f"n{i}", f"note {i}\n")
    await _configure(client, a)
    before = (await client.post("/api/v1/sync/run", json={})).json()["commit"]
    assert before

    a.delete_knowledge("notes", "n0")
    deleted = await client.post("/api/v1/sync/run", json={})
    assert deleted.json()["status"] == "ok", deleted.json()
    assert a.read_knowledge("notes", "n0") is None
    a.write_knowledge("notes", "since", "gained after the deletion\n")

    r = await client.post("/api/v1/sync/restore", json={"at": before})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # A round abbreviates the sha it reports; a restore names the revision in full.
    assert body["commit"] == await a.mirror.resolve_revision(before)
    assert body["applied"]["added"] == 1
    assert body["applied"]["deleted"] == 0  # a restore never throws work away
    assert a.read_knowledge("notes", "n0") == "note 0\n"
    assert a.read_knowledge("notes", "since") == "gained after the deletion\n"


async def test_restore_without_a_remote_is_409(client) -> None:
    r = await client.post("/api/v1/sync/restore", json={"at": None})

    assert r.status_code == 409
    assert _code(r) == "SYNC_NOTHING_TO_ROLL_BACK"


# --- a remote this build cannot read ----------------------------------------


async def test_a_run_against_a_newer_layout_fails_and_says_why(client, fleet) -> None:
    """A round reports, it does not raise: the worker drives the same call on a
    timer, so the refusal arrives as a recorded failed round carrying the
    sentence that tells the user what to do about it."""
    a, _b = fleet
    a.write_knowledge("notes", "mine", "my body\n")
    await _configure(client, a)
    assert (await client.post("/api/v1/sync/run", json={})).json()["status"] == "ok"

    another_coffer_pushes(
        a.remote_url, layout=SCHEMA_VERSION + 1, adding="knowledge/notes/newer.md"
    )

    r = await client.post("/api/v1/sync/run", json={})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed", body
    assert str(SCHEMA_VERSION + 1) in body["error"] and "upgrade" in body["error"]
    assert a.read_knowledge("notes", "newer") is None
    assert a.read_knowledge("notes", "mine") == "my body\n"


async def test_rebuilding_from_a_newer_layout_is_409(client, fleet) -> None:
    """A rebuild is a user asking for something now, so the refusal keeps its
    code and reaches them as one: this vault would *become* that tree, which
    makes it the last place to guess at a layout."""
    a, _b = fleet
    a.write_knowledge("notes", "mine", "my body\n")
    await _configure(client, a)
    assert (await client.post("/api/v1/sync/run", json={})).json()["status"] == "ok"

    another_coffer_pushes(
        a.remote_url, layout=SCHEMA_VERSION + 1, adding="knowledge/notes/newer.md"
    )

    r = await client.post("/api/v1/sync/rebuild", json={})

    assert r.status_code == 409
    assert _code(r) == "SYNC_BUNDLE_TOO_NEW"
    assert a.read_knowledge("notes", "mine") == "my body\n", "the vault must be untouched"


# --- status -----------------------------------------------------------------


async def test_status_on_a_fresh_vault_still_names_this_machine(client) -> None:
    r = await client.get("/api/v1/sync/status")

    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["remote"] is None
    assert body["last_run"] is None
    assert body["machine_id"] == MACHINE_A
    assert body["machine_id_is_derived"] is True


async def test_status_reports_the_remote_and_the_last_round(client, fleet) -> None:
    a, _b = fleet
    a.write_knowledge("notes", "one", "first note\n")
    await _configure(client, a)
    run = (await client.post("/api/v1/sync/run", json={})).json()

    body = (await client.get("/api/v1/sync/status")).json()

    assert body["configured"] is True
    assert body["remote"]["url"] == a.remote_url
    assert body["remote"]["branch"] == DEFAULT_BRANCH
    assert body["last_run"]["status"] == "ok"
    assert body["last_run"]["commit"] == run["commit"]
    assert body["last_run"]["published"] == run["published"]


# --- the run history ---------------------------------------------------------


async def test_runs_on_a_fresh_vault_is_empty_not_an_error(client) -> None:
    """No remote, no rounds. An empty history is the ordinary state."""
    r = await client.get("/api/v1/sync/runs")

    assert r.status_code == 200
    assert r.json() == {"runs": []}


async def test_every_round_lands_in_the_history_newest_first(client, fleet) -> None:
    """The whole point of the history: rounds after the first one survive.

    Three rounds, and the second is the only one that changed anything. On the
    old surface the third round's "nothing changed" was all a user could see,
    and the round that published the note was gone.
    """
    a, _b = fleet
    await _configure(client, a)
    first = (await client.post("/api/v1/sync/run", json={})).json()
    a.write_knowledge("notes", "one", "first note\n")
    second = (await client.post("/api/v1/sync/run", json={})).json()
    third = (await client.post("/api/v1/sync/run", json={})).json()

    runs = (await client.get("/api/v1/sync/runs")).json()["runs"]

    assert [r["status"] for r in runs] == [third["status"], second["status"], first["status"]]
    assert runs[1]["published"] == second["published"]
    assert runs[1]["published"]["added"] >= 1
    # Ids are what a surface keys a row on, so they must be distinct even when
    # two rounds are otherwise identical values.
    assert len({r["id"] for r in runs}) == 3


async def test_a_history_row_carries_everything_the_status_round_did_plus_when(
    client, fleet
) -> None:
    """``RunRecordOut`` is a superset of ``RoundOut``, asserted field by field.

    The two surfaces must describe the same round identically; the timestamps
    are the only thing the history adds.
    """
    a, _b = fleet
    a.write_knowledge("notes", "one", "first note\n")
    await _configure(client, a)
    run = (await client.post("/api/v1/sync/run", json={})).json()

    record = (await client.get("/api/v1/sync/runs")).json()["runs"][0]

    assert {k: record[k] for k in run} == run
    assert record["started_at"] <= record["finished_at"]


async def test_the_newest_history_row_and_the_status_round_are_the_same_round(
    client, fleet
) -> None:
    """Two surfaces, one moment. They are written in one transaction, so a
    user reading Status and a user reading History must never be looking at
    different rounds — which a second write, or a second projection, is how
    this would stop being true."""
    a, _b = fleet
    a.write_knowledge("notes", "one", "first note\n")
    await _configure(client, a)
    await client.post("/api/v1/sync/run", json={})
    a.write_knowledge("notes", "two", "second note\n")
    await client.post("/api/v1/sync/run", json={})

    newest = (await client.get("/api/v1/sync/runs")).json()["runs"][0]
    last = (await client.get("/api/v1/sync/status")).json()["last_run"]

    assert {k: newest[k] for k in last} == last


async def test_runs_caps_what_one_read_returns(client, fleet) -> None:
    a, _b = fleet
    await _configure(client, a)
    await client.post("/api/v1/sync/run", json={})
    await client.post("/api/v1/sync/run", json={})

    assert len((await client.get("/api/v1/sync/runs?limit=1")).json()["runs"]) == 1
    assert (await client.get("/api/v1/sync/runs?limit=0")).status_code == 422
    assert (await client.get("/api/v1/sync/runs?limit=501")).status_code == 422


# --- machines ---------------------------------------------------------------


async def test_machines_without_a_remote_is_empty(client) -> None:
    r = await client.get("/api/v1/sync/machines")

    assert r.status_code == 200
    assert r.json() == {"machines": []}


async def test_machines_lists_every_machine_sharing_the_vault(client, fleet) -> None:
    a, b = fleet
    b.write_knowledge("notes", "from-b", "desktop\n")
    await b.converge()
    await b.converge()
    await _configure(client, a)
    assert (await client.post("/api/v1/sync/run", json={})).json()["status"] == "ok"

    r = await client.get("/api/v1/sync/machines")

    assert r.status_code == 200
    rows = {m["machine_id"]: m for m in r.json()["machines"]}
    assert set(rows) == {MACHINE_A, MACHINE_B}
    assert rows[MACHINE_A]["is_self"] is True
    assert rows[MACHINE_A]["name"] == "laptop"
    assert rows[MACHINE_A]["coffer_version"] == "test"
    assert rows[MACHINE_A]["key_matches"] is True
    assert rows[MACHINE_B]["is_self"] is False
    assert rows[MACHINE_B]["name"] == "desktop"
    # Two machines that never exchanged a key cannot read each other's ciphertext.
    assert rows[MACHINE_B]["key_matches"] is False
    assert rows[MACHINE_B]["last_converged_on"]


async def test_rename_self_renames_this_machine(client, fleet) -> None:
    a, _b = fleet
    await _configure(client, a)

    r = await client.patch("/api/v1/sync/machines/self", json={"name": "kitchen table"})

    assert r.status_code == 200
    body = r.json()
    assert body["machine_id"] == MACHINE_A
    assert body["is_self"] is True
    assert body["name"] == "kitchen table"
    assert a.name == "kitchen table"


async def test_retiring_this_machine_is_refused(client, fleet) -> None:
    a, _b = fleet
    await _configure(client, a)

    r = await client.delete(f"/api/v1/sync/machines/{MACHINE_A}")

    assert r.status_code == 422
    assert _code(r) == "SYNC_CANNOT_RETIRE_SELF"


async def test_retiring_a_machine_removes_its_descriptor_and_nothing_else(client, fleet) -> None:
    """The answer has one half, because the operation has one effect.

    It used to carry a ``scopes_updated`` count: retiring a machine also
    rewrote every scope that named it. No scope can name a machine now — reach
    is machine-local — so there is nothing else to rewrite and nothing else to
    report.
    """
    a, b = fleet
    await b.converge()
    await b.converge()
    await a.register("mcp_server", "shared")
    await _configure(client, a)
    assert (await client.post("/api/v1/sync/run", json={})).json()["status"] == "ok"
    await a.set_scope("mcp_server", "shared", Scope(agents=["claude-code"]))

    r = await client.delete(f"/api/v1/sync/machines/{MACHINE_B}")

    assert r.status_code == 200
    assert r.json() == {"removed": True}
    remaining = {
        m["machine_id"] for m in (await client.get("/api/v1/sync/machines")).json()["machines"]
    }
    assert remaining == {MACHINE_A}
    resource = await a.find("mcp_server", "shared")
    assert resource is not None
    assert resource.scope == Scope(agents=["claude-code"]), (
        "retiring a machine rewrote a resource's reach"
    )


# --- the master key ---------------------------------------------------------


async def test_key_fingerprint_is_short_and_is_not_the_key(client, fleet) -> None:
    a, _b = fleet

    r = await client.get("/api/v1/sync/key/fingerprint")

    assert r.status_code == 200
    fingerprint = r.json()["fingerprint"]
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 12
    key = a.master_key.export_key()
    assert key is not None
    assert fingerprint not in key.decode()
    assert fingerprint == a.key_fingerprint()


async def test_key_export_hands_back_material_and_import_takes_it_again(client, fleet) -> None:
    """The key crosses as material, not as a path the daemon writes: a browser
    has no path to hand over, and the caller decides where the bytes land."""
    a, _b = fleet

    exported = await client.post("/api/v1/sync/key/export", json={})

    assert exported.status_code == 200
    material = exported.json()["material"]
    key = a.master_key.export_key()
    assert key is not None
    assert material == key.decode("utf-8")

    imported = await client.post("/api/v1/sync/key/import", json={"material": material})

    assert imported.status_code == 200
    assert imported.json() == {"locked_refs": []}
    assert a.master_key.export_key() == key


async def test_key_import_reports_what_it_still_cannot_read(client, fleet) -> None:
    a, b = fleet
    a.set_credential("mcp/files/token", "s3cret-value")
    await a.register("mcp_server", "files", {"value": "f", "credential_ref": "mcp/files/token"})
    await _configure(client, a)
    assert (await client.post("/api/v1/sync/run", json={})).json()["status"] == "ok"
    # B absorbs A's ciphertext without A's key, so the ref is locked there.
    await b.converge()
    await b.converge()
    assert b.credentials.locked_refs() == ["mcp/files/token"]

    other = b.master_key.export_key()
    assert other is not None
    r = await client.post("/api/v1/sync/key/import", json={"material": other.decode("utf-8")})

    assert r.status_code == 200
    # A now holds B's key, so A's own ciphertext is the unreadable one.
    assert r.json()["locked_refs"] == ["mcp/files/token"]


async def test_key_import_of_empty_material_is_422(client) -> None:
    r = await client.post("/api/v1/sync/key/import", json={"material": "   "})

    assert r.status_code == 422
    assert _code(r) == "MASTER_KEY_FILE_INVALID"


async def test_key_import_of_junk_material_is_422(client) -> None:
    r = await client.post("/api/v1/sync/key/import", json={"material": "not-a-fernet-key"})

    assert r.status_code == 422
    assert _code(r) == "MASTER_KEY_FILE_INVALID"


# --- the guards around every route ------------------------------------------


async def test_a_wrong_token_is_401(client) -> None:
    r = await client.get("/api/v1/sync/status", headers={"X-Coffer-Token": "wrong"})

    assert r.status_code == 401


async def test_the_bundle_directory_routes_are_gone(client, tmp_path) -> None:
    """Writing a bundle to a directory and reading one back was a wholesale
    overwrite with no base — the 2026-07-10 mutual deletion — and it has no
    place beside the diff-based round (spec ``## Out of scope``)."""
    body = {"path": str(tmp_path / "bundle")}

    assert (await client.post("/api/v1/sync/export", json=body)).status_code == 404
    assert (await client.post("/api/v1/sync/import", json=body)).status_code == 404

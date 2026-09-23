"""Integration tests for ``coffer sync ...`` (spec vault-sync ``## Surfaces``).

The real CLI is driven against a minimal app carrying only the sync router, so
these stay a test of the command surface rather than of daemon composition. The
service behind that router is the production :class:`ConvergeService` built by
``tests/integration/sync/harness.py`` — two whole vaults and one real bare git
repository — so a command that reports a round is reporting what git did, and a
command with a side effect can be checked against the vault and the remote.

There is no ``export`` or ``import`` verb any more: writing a bundle to a
directory and reading one back was a wholesale overwrite with no base, and it
has no place beside the diff-based round. That they are gone is asserted, and
nothing else in this file mentions them.

Rich soft-wraps a long temporary path, so every assertion here matches a short
leaf substring rather than a whole path.
"""

from __future__ import annotations

import asyncio
import dataclasses
import pathlib
import stat
from collections.abc import Awaitable, Iterator
from datetime import UTC
from datetime import datetime as dt
from typing import Any, TypeVar

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.domain.scope import Scope
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.sync_routes import (
    router as sync_router,
)
from coffer.surfaces.http.sync_routes import (
    set_machine_registry,
    set_sync_service,
)
from tests.integration.sync.harness import MACHINE_A, MACHINE_B, VaultMachine, two_machines

pytestmark = pytest.mark.timeout(180)

_runner = CliRunner()
_TOKEN = "test-token-sync-cli"

#: The deletion guard's default share is 20%, so one of five is at the
#: threshold rather than over it — a plain deletion that is allowed to travel.
_ROOMY = 5

T = TypeVar("T")


class Fleet:
    """Machine ``a`` is the one the CLI talks to; ``b`` is its peer."""

    def __init__(self, a: VaultMachine, b: VaultMachine, loop: asyncio.AbstractEventLoop) -> None:
        self.a = a
        self.b = b
        self._loop = loop

    def run(self, awaitable: Awaitable[T]) -> T:
        """Drive one harness coroutine from this synchronous test."""
        return self._loop.run_until_complete(awaitable)

    def invoke(self, *argv: str) -> Any:
        return _runner.invoke(cli_app, list(argv))

    def ok(self, *argv: str) -> Any:
        result = self.invoke(*argv)
        assert result.exit_code == 0, f"{argv}: {result.output}"
        return result


@pytest.fixture
def fleet(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Fleet]:
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "pinned-knowledge"))
    monkeypatch.setenv("COFFER_SKILLS_ROOT", str(tmp_path / "pinned-skills"))
    # Rich wraps at 80 columns by default, which folds a tmp path mid-word.
    monkeypatch.setenv("COLUMNS", "200")

    loop = asyncio.new_event_loop()
    a, b = loop.run_until_complete(two_machines(tmp_path))
    set_sync_service(a.service())
    set_machine_registry(a.registry)

    app = FastAPI()
    app.include_router(sync_router)
    err_handlers.register(app)
    set_active_token(_TOKEN)

    info = DaemonInfo(
        version=1, pid=1, port=59820, token=_TOKEN, started_at=dt.now(tz=UTC), binary_path="/test"
    )
    daemon = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    daemon.__enter__()

    class _Persistent:
        """``client_or_exit`` hands out a client each command closes; the
        TestClient must outlive them all, so closing it is a no-op here."""

        def __enter__(self) -> _Persistent:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def __getattr__(self, item: str) -> Any:
            return getattr(daemon, item)

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_Persistent(), info))

    try:
        yield Fleet(a, b, loop)
    finally:
        daemon.__exit__(None, None, None)
        set_active_token(None)
        loop.run_until_complete(a.close())
        loop.run_until_complete(b.close())
        loop.close()


def _seed_and_publish(fleet: Fleet, count: int = _ROOMY) -> None:
    for i in range(count):
        fleet.a.write_knowledge("notes", f"n{i}", f"original {i}\n")
    fleet.ok("sync", "remote", "set", fleet.a.remote_url)
    fleet.ok("sync", "adopt", "--yes")


# --- the remote -------------------------------------------------------------


def test_remote_show_on_a_fresh_vault_says_there_is_none(fleet: Fleet) -> None:
    result = fleet.ok("sync", "remote", "show")

    assert "no sync remote configured" in result.output


def test_remote_set_probes_the_remote_and_stores_the_defaults(fleet: Fleet) -> None:
    result = fleet.ok("sync", "remote", "set", fleet.a.remote_url)

    assert "branch" in result.output
    assert "every 3600s" in result.output
    assert "credentials excluded" in result.output
    assert "enabled" in result.output
    assert "working tree" in result.output

    shown = fleet.ok("sync", "remote", "show")
    assert "every 3600s" in shown.output
    assert "no sync remote configured" not in shown.output


def test_remote_set_carries_the_options_it_was_given(fleet: Fleet) -> None:
    result = fleet.ok(
        "sync",
        "remote",
        "set",
        fleet.a.remote_url,
        "--interval",
        "60",
        "--with-credentials",
    )

    assert "every 60s" in result.output
    assert "credentials included" in result.output


def test_remote_set_refuses_a_remote_it_cannot_reach(fleet: Fleet, tmp_path) -> None:
    result = fleet.invoke("sync", "remote", "set", str(tmp_path / "no-such.git"))

    assert result.exit_code != 0
    assert "no sync remote configured" in fleet.ok("sync", "remote", "show").output


def test_remote_clear_is_idempotent(fleet: Fleet) -> None:
    fleet.ok("sync", "remote", "set", fleet.a.remote_url)

    cleared = fleet.ok("sync", "remote", "clear")
    again = fleet.ok("sync", "remote", "clear")

    assert "cleared" in cleared.output
    assert "nothing to clear" in again.output


# --- rounds -----------------------------------------------------------------


def test_sync_now_without_a_remote_reports_a_disabled_round(fleet: Fleet) -> None:
    result = fleet.ok("sync", "now")

    assert "disabled" in result.output


def test_sync_now_publishes_the_vault_and_says_what_it_did(fleet: Fleet) -> None:
    fleet.ok("sync", "remote", "set", fleet.a.remote_url)
    fleet.ok("sync", "adopt", "--yes")
    fleet.a.write_knowledge("notes", "one", "first note\n")

    result = fleet.ok("sync", "now")

    assert "ok" in result.output
    assert "applied here: nothing" in result.output
    assert "published: added" in result.output
    assert "commit:" in result.output
    assert "knowledge/notes/one.md" in fleet.run(fleet.a.remote_paths())


def test_sync_now_and_status_on_a_machine_that_has_not_joined_point_at_adopt(
    fleet: Fleet,
) -> None:
    fleet.b.write_knowledge("notes", "from-b", "written on the desktop\n")
    fleet.run(fleet.b.adopt())
    fleet.ok("sync", "remote", "set", fleet.a.remote_url)

    now = fleet.ok("sync", "now")
    status = fleet.invoke("sync", "status")

    assert "awaiting_join" in now.output
    for result in (now, status):
        assert "has not joined this remote yet" in result.output
        assert "coffer sync adopt" in result.output
        # The join the round detected, reported rather than applied.
        assert "as a new machine" in result.output
        assert "documents the remote changed since: 1" in result.output
    assert status.exit_code != 0
    assert fleet.a.read_knowledge("notes", "from-b") is None


def test_status_lists_what_cannot_apply_on_this_machine(fleet: Fleet) -> None:
    fleet.run(fleet.b.register("mcp_server", "wrong-machine", {"value": "never"}))
    fleet.run(fleet.b.adopt())
    fleet.a.gate.refuse_value = "never"
    fleet.a.gate.refuse_permanently = True
    fleet.ok("sync", "remote", "set", fleet.a.remote_url)

    joined = fleet.ok("sync", "adopt", "--yes")
    status = fleet.invoke("sync", "status")

    path = fleet.run(fleet.b.doc_path("mcp_server", "wrong-machine"))
    assert "could not apply" not in joined.output
    for result in (joined, status):
        assert "not applicable here" in result.output
        assert path in result.output


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a new machine takes the union and deletes nothing"
)
def test_adopt_takes_the_union_from_a_remote_holding_other_work(fleet: Fleet) -> None:
    fleet.b.write_knowledge("notes", "from-b", "written on the desktop\n")
    fleet.run(fleet.b.adopt())
    fleet.run(fleet.b.converge())
    fleet.a.write_knowledge("notes", "from-a", "written on the laptop\n")

    result = fleet.ok("sync", "adopt", fleet.a.remote_url, "--yes")

    assert "joined this remote as a" in result.output
    assert "new" in result.output
    assert "returning" not in result.output
    assert fleet.a.read_knowledge("notes", "from-b") == "written on the desktop\n"
    assert fleet.a.read_knowledge("notes", "from-a") == "written on the laptop\n"
    assert {"knowledge/notes/from-a.md", "knowledge/notes/from-b.md"} <= fleet.run(
        fleet.a.remote_paths()
    )


def test_adopt_keep_local_answers_an_otherwise_unrecoverable_join(fleet: Fleet) -> None:
    """A first round publishes a descriptor naming no commit; a reinstall on
    that same day leaves this machine's base unrecoverable."""
    fleet.a.write_knowledge("notes", "one", "first note\n")
    fleet.ok("sync", "remote", "set", fleet.a.remote_url)
    fleet.ok("sync", "adopt", "--yes")
    fleet.a.state.forget()

    refused = fleet.invoke("sync", "adopt", "--yes")
    assert refused.exit_code != 0
    assert "gone from the remote's history" in refused.output
    assert "--keep-local" in refused.output
    assert "joined this remote" not in refused.output

    chosen = fleet.ok("sync", "adopt", "--keep-local", "--yes")

    assert "joined this remote as a" in chosen.output
    assert fleet.a.read_knowledge("notes", "one") == "first note\n"


def _returning_after_the_remote_moved(fleet: Fleet) -> None:
    """A converged twice, then lost its pointer; the remote moved on since.

    A's descriptor records the base its second round started from — the commit
    its first round reached — so the remote has changed three notes since:
    ``mine`` and ``while-away`` (which A itself went on to hold) and ``later``.
    """
    fleet.a.write_knowledge("notes", "shared", "one\n")
    fleet.ok("sync", "remote", "set", fleet.a.remote_url)
    fleet.ok("sync", "adopt", "--yes")
    fleet.a.write_knowledge("notes", "mine", "only on this machine\n")
    fleet.run(fleet.b.adopt())
    fleet.b.write_knowledge("notes", "while-away", "written while a was gone\n")
    fleet.run(fleet.b.converge())
    # A second round on the same day stamps a descriptor naming a commit, so the
    # base is recoverable: this is the returning case, not the ambiguous one.
    fleet.ok("sync", "now")
    fleet.b.write_knowledge("notes", "later", "written after a's last round\n")
    fleet.run(fleet.b.converge())
    fleet.a.state.forget()


def test_adopt_states_the_join_and_asks_before_applying(
    fleet: Fleet, monkeypatch: pytest.MonkeyPatch
) -> None:
    _returning_after_the_remote_moved(fleet)
    monkeypatch.setattr("coffer.surfaces.cli.sync_join.interactive", lambda: True)

    declined = _runner.invoke(cli_app, ["sync", "adopt"], input="n\n")

    assert declined.exit_code != 0
    assert "returning" in declined.output
    assert "last converged here: 2" in declined.output
    assert "documents the remote changed since: 3" in declined.output
    assert "documents this vault holds:" in declined.output
    assert "Join this remote?" in declined.output
    assert fleet.a.read_knowledge("notes", "later") is None
    assert fleet.run(fleet.a.state.pointer()) is None

    accepted = _runner.invoke(cli_app, ["sync", "adopt"], input="y\n")

    assert accepted.exit_code == 0, accepted.output
    assert "joined this remote as a" in accepted.output
    assert fleet.a.read_knowledge("notes", "later") == "written after a's last round\n"


def test_adopt_without_a_terminal_refuses_unless_told_yes(fleet: Fleet) -> None:
    fleet.b.write_knowledge("notes", "from-b", "written on the desktop\n")
    fleet.run(fleet.b.adopt())

    refused = fleet.invoke("sync", "adopt", fleet.a.remote_url)

    assert refused.exit_code != 0
    assert "new" in refused.output
    assert "refusing to join without confirmation" in refused.output
    assert fleet.a.read_knowledge("notes", "from-b") is None
    assert fleet.run(fleet.a.state.pointer()) is None

    fleet.ok("sync", "adopt", "--yes")
    assert fleet.a.read_knowledge("notes", "from-b") == "written on the desktop\n"


# --- a round the deletion guard held ----------------------------------------


def _hold_a_deletion(fleet: Fleet) -> Any:
    fleet.a.write_knowledge("notes", "only", "the only note\n")
    fleet.ok("sync", "remote", "set", fleet.a.remote_url)
    fleet.ok("sync", "adopt", "--yes")
    fleet.a.delete_knowledge("notes", "only")
    held = fleet.ok("sync", "now")
    assert "awaiting_confirmation" in held.output, held.output
    return held


def test_a_held_round_shows_what_it_would_delete(fleet: Fleet) -> None:
    held = _hold_a_deletion(fleet)

    assert "would delete the following from the remote" in held.output
    assert "knowledge: 1 of 1" in held.output
    assert "knowledge/notes/only.md" in held.output
    assert "coffer sync confirm" in held.output
    assert "knowledge/notes/only.md" in fleet.run(fleet.a.remote_paths())


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a held vault says so where the user already is"
)
def test_status_exits_non_zero_while_a_round_is_held(fleet: Fleet) -> None:
    """A held vault converges no further, so the exit code has to say so.

    The first hold in the field stood for four days because the only surface
    that reported it was a page nobody had reason to open (spec vault-sync
    FR-096). A non-zero exit is what lets a prompt, a cron line or a monitor
    notice without reading the text.
    """
    _hold_a_deletion(fleet)

    result = fleet.invoke("sync", "status")

    assert result.exit_code == 1, result.output
    assert "awaiting_confirmation" in result.output


def test_status_exits_zero_once_sync_is_switched_off(fleet: Fleet) -> None:
    """Switching sync off is an answer too, and the exit code has to take it.

    A disabled remote makes a round return ``disabled`` WITHOUT recording it,
    so ``last_run`` keeps reporting the hold. Without this a user who met the
    hold by turning sync off rather than by answering it would have every
    check that asks fail for ever, with no way back but to turn it on again.
    """
    held = _hold_a_deletion(fleet)
    assert "awaiting_confirmation" in held.output
    assert fleet.invoke("sync", "status").exit_code == 1

    remote = fleet.run(fleet.a.service().get_remote())
    assert remote is not None
    fleet.run(fleet.a.service().set_remote(dataclasses.replace(remote, enabled=False)))

    result = fleet.invoke("sync", "status")

    assert result.exit_code == 0, result.output
    # The round it is still carrying has NOT been rewritten — only the
    # question of whether anyone should be told about it has changed.
    assert "awaiting_confirmation" in result.output


def test_status_exits_zero_once_the_hold_is_answered(fleet: Fleet) -> None:
    """And it must go back to zero, or the signal is a stuck alarm."""
    _hold_a_deletion(fleet)
    fleet.ok("sync", "confirm")

    result = fleet.invoke("sync", "status")

    assert result.exit_code == 0, result.output


def test_confirm_lets_the_held_deletion_through(fleet: Fleet) -> None:
    _hold_a_deletion(fleet)

    result = fleet.ok("sync", "confirm")

    assert "published: deleted 1" in result.output
    assert "knowledge/notes/only.md" not in fleet.run(fleet.a.remote_paths())


def test_reject_discards_the_held_round(fleet: Fleet) -> None:
    _hold_a_deletion(fleet)

    result = fleet.ok("sync", "reject")

    assert "discarded" in result.output
    assert "the vault is unchanged" in result.output
    assert "knowledge/notes/only.md" in fleet.run(fleet.a.remote_paths())


def test_confirm_with_nothing_held_exits_non_zero(fleet: Fleet) -> None:
    assert fleet.invoke("sync", "confirm").exit_code != 0


def test_reject_with_nothing_held_exits_non_zero(fleet: Fleet) -> None:
    assert fleet.invoke("sync", "reject").exit_code != 0


# --- undoing ----------------------------------------------------------------


def test_rollback_with_nothing_to_roll_back_exits_non_zero(fleet: Fleet) -> None:
    assert fleet.invoke("sync", "rollback").exit_code != 0


def test_rollback_undoes_the_round_that_was_just_applied(fleet: Fleet) -> None:
    _seed_and_publish(fleet)
    fleet.run(fleet.b.adopt())
    fleet.run(fleet.b.converge())
    fleet.b.write_knowledge("notes", "n0", "rewritten by B\n")
    fleet.b.write_knowledge("notes", "extra", "new from B\n")
    fleet.run(fleet.b.converge())
    fleet.ok("sync", "adopt", "--yes")
    assert fleet.a.read_knowledge("notes", "n0") == "rewritten by B\n"

    result = fleet.ok("sync", "rollback")

    assert "ok" in result.output
    assert fleet.a.read_knowledge("notes", "n0") == "original 0\n"
    assert fleet.a.read_knowledge("notes", "extra") is None


def test_restore_at_a_revision_brings_a_deleted_note_back(fleet: Fleet) -> None:
    _seed_and_publish(fleet)
    before = fleet.run(fleet.a.mirror.head())
    assert before
    fleet.a.delete_knowledge("notes", "n0")
    fleet.ok("sync", "adopt", "--yes")
    assert fleet.a.read_knowledge("notes", "n0") is None
    fleet.a.write_knowledge("notes", "since", "gained after the deletion\n")

    result = fleet.ok("sync", "restore", "--at", before)

    assert "applied here: added 1" in result.output
    assert fleet.a.read_knowledge("notes", "n0") == "original 0\n"
    # A restore reaches back for what was lost; it does not throw away the rest.
    assert fleet.a.read_knowledge("notes", "since") == "gained after the deletion\n"


# --- status -----------------------------------------------------------------


def test_status_on_an_unconfigured_vault_still_prints_the_machine_id(fleet: Fleet) -> None:
    result = fleet.ok("sync", "status")

    assert "no sync remote configured" in result.output
    assert f"this machine: {MACHINE_A}" in result.output
    assert "no round yet" in result.output


def test_status_after_a_round_reports_the_remote_and_that_round(fleet: Fleet) -> None:
    fleet.a.write_knowledge("notes", "one", "first note\n")
    fleet.ok("sync", "remote", "set", fleet.a.remote_url)
    fleet.ok("sync", "adopt", "--yes")

    result = fleet.ok("sync", "status")

    assert "no sync remote configured" not in result.output
    assert "every 3600s" in result.output
    assert f"this machine: {MACHINE_A}" in result.output
    assert "published: added" in result.output
    assert "no round yet" not in result.output


# --- machines ---------------------------------------------------------------


def test_machine_list_with_no_machines_yet_says_how_to_publish_this_one(fleet: Fleet) -> None:
    result = fleet.ok("sync", "machine", "list")

    assert "no machines yet" in result.output
    # Only a joined machine's round publishes it, and this one has not joined.
    assert "coffer sync adopt" in result.output
    assert "sync now" not in result.output


def test_machine_list_marks_this_machine_and_shows_its_peers(fleet: Fleet) -> None:
    fleet.b.write_knowledge("notes", "from-b", "desktop\n")
    fleet.run(fleet.b.adopt())
    fleet.run(fleet.b.converge())
    fleet.ok("sync", "remote", "set", fleet.a.remote_url)
    fleet.ok("sync", "adopt", "--yes")

    result = fleet.ok("sync", "machine", "list")

    assert "laptop" in result.output
    assert "(this machine)" in result.output
    assert "desktop" in result.output
    assert MACHINE_A[:8] in result.output
    assert MACHINE_B[:8] in result.output
    # Two machines that never exchanged a key cannot read each other's ciphertext.
    assert "different" in result.output


def test_machine_rename_renames_this_machine(fleet: Fleet) -> None:
    fleet.ok("sync", "remote", "set", fleet.a.remote_url)

    result = fleet.ok("sync", "machine", "rename", "kitchen table")

    assert "renamed" in result.output
    assert fleet.a.name == "kitchen table"


def test_machine_remove_retires_a_peer_and_touches_nothing_else(fleet: Fleet) -> None:
    """Retiring is one change with one effect: the descriptor goes.

    It used to report a second number — how many scopes it had rewritten to
    drop the retired id — and there is no such number now. Nothing in the vault
    names a machine, because reach is machine-local, so a retirement has
    nothing else to reach for and says so by saying only one thing.
    """
    fleet.run(fleet.b.adopt())
    fleet.run(fleet.b.converge())
    fleet.run(fleet.a.register("mcp_server", "shared"))
    fleet.ok("sync", "remote", "set", fleet.a.remote_url)
    fleet.ok("sync", "adopt", "--yes")
    fleet.run(fleet.a.set_scope("mcp_server", "shared", Scope(agents=["claude-code"])))

    result = fleet.ok("sync", "machine", "remove", MACHINE_B)

    assert "retired" in result.output
    assert "scopes updated" not in result.output
    assert MACHINE_B[:8] not in fleet.ok("sync", "machine", "list").output
    resource = fleet.run(fleet.a.find("mcp_server", "shared"))
    assert resource is not None
    assert resource.scope == Scope(agents=["claude-code"]), (
        "retiring a machine rewrote a resource's reach"
    )


# --- the master key ---------------------------------------------------------


def test_key_fingerprint_prints_the_short_hash(fleet: Fleet) -> None:
    result = fleet.ok("sync", "key", "fingerprint")

    fingerprint = fleet.a.key_fingerprint()
    assert fingerprint is not None
    assert fingerprint in result.output


def test_key_export_writes_a_private_file_the_import_reads_back(fleet: Fleet, tmp_path) -> None:
    target = tmp_path / "carried" / "master.key"

    exported = fleet.ok("sync", "key", "export", str(target))

    assert "mode 0600" in exported.output
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    key = fleet.a.master_key.export_key()
    assert key is not None
    assert target.read_text(encoding="utf-8") == key.decode("utf-8")

    imported = fleet.ok("sync", "key", "import", str(target))

    assert "installed" in imported.output
    assert "every credential decrypts here" in imported.output
    assert fleet.a.master_key.export_key() == key


def test_key_import_names_what_it_still_cannot_read(fleet: Fleet, tmp_path) -> None:
    fleet.a.set_credential("mcp/files/token", "s3cret-value")
    fleet.run(
        fleet.a.register("mcp_server", "files", {"value": "f", "credential_ref": "mcp/files/token"})
    )
    other = fleet.b.master_key.export_key()
    assert other is not None
    carried = tmp_path / "from-desktop.key"
    carried.write_text(other.decode("utf-8"), encoding="utf-8")

    result = fleet.ok("sync", "key", "import", str(carried))

    # A now holds B's key, so A's own ciphertext is the unreadable one.
    assert "still locked" in result.output
    assert "mcp/files/token" in result.output


# --- what the surface no longer offers --------------------------------------


def test_the_bundle_directory_commands_are_gone(fleet: Fleet, tmp_path) -> None:
    """Writing a bundle to a directory and reading one back was a wholesale
    overwrite with no base, and it has no place beside the diff-based round."""
    assert fleet.invoke("sync", "export", str(tmp_path / "bundle")).exit_code != 0
    assert fleet.invoke("sync", "import", str(tmp_path / "bundle")).exit_code != 0


def test_conflict_advice_names_the_step_this_machine_can_take(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from coffer.surfaces.cli import sync_cmd

    monkeypatch.setenv("COLUMNS", "200")
    conflicted = {"status": "conflict", "join": "new", "conflicts": ["knowledge/notes/x.md"]}

    sync_cmd._print_round(conflicted, joined=False)
    not_joined = capsys.readouterr().out
    sync_cmd._print_round(conflicted, joined=True)
    joined = capsys.readouterr().out

    assert "then run 'coffer sync adopt'" in not_joined
    assert "then run 'coffer sync now'" in joined

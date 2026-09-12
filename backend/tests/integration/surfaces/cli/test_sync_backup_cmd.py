"""Integration tests for `coffer sync remote|push|restore|status`.

Spec vault-export-import ``## Backup`` / ``### Restore`` / ``## Surfaces``.

The CLI is driven against the real sync router carrying a stub backup service,
so what is asserted is the command surface: the request each flag produces, and
what the user is shown of the response. Git itself is out of scope here — the
adapter's behaviour against a real repository is pinned in
``tests/integration/sync/test_git_mirror.py``, and a CLI test that shelled out
to git would only re-test that.
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime as dt
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.domain.sync.backup import BackupRemote, BackupRun, BackupRunStatus
from coffer.domain.sync.models import AreaCount, ImportSummary
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.sync_routes import router as sync_router
from coffer.surfaces.http.sync_routes import set_backup_service

_runner = CliRunner()
_TOKEN = "test-token-sync-backup-cli"
_URL = "https://example.invalid/vault.git"
#: Shaped like a real push token, so "the output does not contain the secret"
#: is a claim about a distinctive string rather than an everyday word.
_PUSH_SECRET = "placeholder-not-a-real-secret-3f7c1a"
_CRED_REF = "sync/backup/token"


class _StubBackupService:
    """Records what the routes asked of it, answers with canned results.

    Duck-typed rather than a subclass: the CLI's contract is the wire shape the
    routes produce, and a stub that cannot accidentally touch git or the
    credential store keeps that the only thing under test.
    """

    def __init__(self) -> None:
        self.remote: BackupRemote | None = None
        self.last_run: BackupRun | None = None
        self.restores: list[dict[str, str | None]] = []
        self.runs = 0
        self.next_run = BackupRun(
            status=BackupRunStatus.OK, commit="abc1234", ran_at=dt(2026, 9, 12, tzinfo=UTC)
        )
        self.next_summary = ImportSummary(
            path="/home/u/.coffer/sync",
            areas=[AreaCount("skills", 3), AreaCount("resources", 7)],
            locked_refs=[],
        )

    async def configure(self, remote: BackupRemote) -> None:
        self.remote = remote

    async def get(self) -> BackupRemote | None:
        return self.remote

    async def clear(self) -> None:
        self.remote = None

    async def status(self) -> tuple[BackupRemote | None, BackupRun | None]:
        return self.remote, self.last_run

    async def run_once(self) -> BackupRun:
        self.runs += 1
        self.last_run = self.next_run
        return self.next_run

    async def restore(self, *, at: str | None = None, from_url: str | None = None) -> ImportSummary:
        self.restores.append({"at": at, "from_url": from_url})
        return self.next_summary


@pytest.fixture
def backup_cli(monkeypatch: pytest.MonkeyPatch) -> Any:
    service = _StubBackupService()
    set_backup_service(service)  # type: ignore[arg-type]

    app = FastAPI()
    app.include_router(sync_router)
    err_handlers.register(app)
    set_active_token(_TOKEN)
    info = DaemonInfo(
        version=1,
        pid=1,
        port=59821,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    fake = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    fake.__enter__()

    class _Persistent:
        """The CLI closes its client per command; the test app outlives that."""

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *a: object) -> None:
            return None

        def __getattr__(self, item: str) -> Any:
            return getattr(fake, item)

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_Persistent(), info))
    yield service
    fake.__exit__(None, None, None)
    set_active_token(None)


# --- remote set ------------------------------------------------------------


def test_remote_set_stores_the_configuration(backup_cli: _StubBackupService) -> None:
    result = _runner.invoke(
        cli_app,
        ["sync", "remote", "set", _URL, "--branch", "backup", "--interval", "900"],
    )
    assert result.exit_code == 0, result.output
    stored = backup_cli.remote
    assert stored is not None
    assert stored.url == _URL
    assert stored.branch == "backup"
    assert stored.interval_seconds == 900
    assert stored.enabled is True
    assert stored.include_credentials is False


def test_remote_set_defaults_match_the_spec(backup_cli: _StubBackupService) -> None:
    assert _runner.invoke(cli_app, ["sync", "remote", "set", _URL]).exit_code == 0
    stored = backup_cli.remote
    assert stored is not None
    assert stored.branch == "main"
    assert stored.interval_seconds == 3600


def test_remote_set_prints_what_a_push_will_contain(backup_cli: _StubBackupService) -> None:
    result = _runner.invoke(cli_app, ["sync", "remote", "set", _URL])
    assert result.exit_code == 0, result.output
    assert "a push will contain" in result.output
    for area in ("knowledge", "skills", "resources", "state"):
        assert area in result.output
    assert "credentials: not included" in result.output


def test_with_credentials_is_stored_and_announced(backup_cli: _StubBackupService) -> None:
    result = _runner.invoke(cli_app, ["sync", "remote", "set", _URL, "--with-credentials"])
    assert result.exit_code == 0, result.output
    stored = backup_cli.remote
    assert stored is not None
    # An opt-in on the remote, not a per-run flag: every later push carries
    # ciphertext without the user re-stating it.
    assert stored.include_credentials is True
    assert "ciphertext" in result.output


def test_push_is_not_a_place_to_opt_into_credentials(backup_cli: _StubBackupService) -> None:
    assert _runner.invoke(cli_app, ["sync", "push", "--with-credentials"]).exit_code != 0


def test_remote_set_keeps_a_credential_ref_configured_elsewhere(
    backup_cli: _StubBackupService,
) -> None:
    backup_cli.remote = BackupRemote(url=_URL, credential_ref=_CRED_REF)
    assert _runner.invoke(cli_app, ["sync", "remote", "set", _URL]).exit_code == 0
    stored = backup_cli.remote
    assert stored is not None
    assert stored.credential_ref == _CRED_REF


# --- remote show / clear ---------------------------------------------------


def test_remote_show_renders_the_reference_never_a_secret(
    backup_cli: _StubBackupService,
) -> None:
    backup_cli.remote = BackupRemote(url=_URL, credential_ref=_CRED_REF)
    result = _runner.invoke(cli_app, ["sync", "remote", "show"])
    assert result.exit_code == 0, result.output
    assert _CRED_REF in result.output
    assert _PUSH_SECRET not in result.output


def test_remote_show_without_a_remote_says_so(backup_cli: _StubBackupService) -> None:
    result = _runner.invoke(cli_app, ["sync", "remote", "show"])
    assert result.exit_code == 0, result.output
    assert "no backup remote configured" in result.output


def test_remote_clear_turns_backup_off(backup_cli: _StubBackupService) -> None:
    backup_cli.remote = BackupRemote(url=_URL)
    result = _runner.invoke(cli_app, ["sync", "remote", "clear"])
    assert result.exit_code == 0, result.output
    assert backup_cli.remote is None
    assert "cleared" in result.output


def test_remote_clear_is_idempotent(backup_cli: _StubBackupService) -> None:
    result = _runner.invoke(cli_app, ["sync", "remote", "clear"])
    assert result.exit_code == 0, result.output
    assert "no backup remote was configured" in result.output


# --- push ------------------------------------------------------------------


def test_push_runs_a_backup_and_reports_the_commit(backup_cli: _StubBackupService) -> None:
    backup_cli.remote = BackupRemote(url=_URL)
    result = _runner.invoke(cli_app, ["sync", "push"])
    assert result.exit_code == 0, result.output
    assert backup_cli.runs == 1
    assert "ok" in result.output
    assert "abc1234" in result.output


def test_a_failed_push_is_reported_and_exits_non_zero(backup_cli: _StubBackupService) -> None:
    backup_cli.remote = BackupRemote(url=_URL, credential_ref=_CRED_REF)
    backup_cli.next_run = BackupRun(
        status=BackupRunStatus.PUSH_FAILED,
        commit="def5678",
        # Already redacted by the time it reaches the wire; the CLI prints it
        # verbatim, so a leak here would be visible.
        error="fatal: could not read Password for 'https://***@example.invalid'",
    )
    result = _runner.invoke(cli_app, ["sync", "push"])
    assert result.exit_code == 1
    assert "push_failed" in result.output
    # The commit is still named: it exists locally and the next run carries it.
    assert "def5678" in result.output
    assert _PUSH_SECRET not in result.output


# --- restore ---------------------------------------------------------------


@pytest.mark.acceptance(
    spec="vault-export-import",
    scenario="restore a resource deleted last week",
)
def test_restore_at_a_date_reaches_the_daemon(backup_cli: _StubBackupService) -> None:
    backup_cli.remote = BackupRemote(url=_URL)
    backup_cli.next_summary = ImportSummary(
        path="/home/u/.coffer/sync",
        areas=[AreaCount("skills", 4)],
    )
    result = _runner.invoke(cli_app, ["sync", "restore", "--at", "2026-09-05"])
    assert result.exit_code == 0, result.output
    # The date the user named is what the daemon resolves against the history;
    # the CLI neither interprets it nor defaults it to the tip.
    assert backup_cli.restores == [{"at": "2026-09-05", "from_url": None}]
    assert "skills" in result.output
    assert "4" in result.output


@pytest.mark.acceptance(
    spec="vault-export-import",
    scenario="restore onto a machine with no working tree",
)
def test_restore_from_a_url_reaches_the_daemon(backup_cli: _StubBackupService) -> None:
    backup_cli.next_summary = ImportSummary(
        path="/home/u/.coffer/sync",
        areas=[AreaCount("resources", 2)],
        locked_refs=["mcp_server:files"],
    )
    result = _runner.invoke(cli_app, ["sync", "restore", "--from", _URL])
    assert result.exit_code == 0, result.output
    assert backup_cli.restores == [{"at": None, "from_url": _URL}]
    # A credential this machine cannot decrypt is reported, not fatal.
    assert "locked credentials" in result.output
    assert "mcp_server:files" in result.output


def test_restore_with_no_flags_restores_the_tip(backup_cli: _StubBackupService) -> None:
    backup_cli.remote = BackupRemote(url=_URL)
    assert _runner.invoke(cli_app, ["sync", "restore"]).exit_code == 0
    assert backup_cli.restores == [{"at": None, "from_url": None}]


def test_nothing_else_implies_a_restore(backup_cli: _StubBackupService) -> None:
    """Restore overwrites local state, so it is only ever the typed command."""
    backup_cli.remote = BackupRemote(url=_URL)
    for argv in (
        ["sync", "push"],
        ["sync", "status"],
        ["sync", "remote", "set", _URL],
        ["sync", "remote", "show"],
        ["sync", "remote", "clear"],
    ):
        _runner.invoke(cli_app, argv)
    assert backup_cli.restores == []


# --- status ----------------------------------------------------------------


def test_status_reports_the_remote_with_no_run_yet(backup_cli: _StubBackupService) -> None:
    backup_cli.remote = BackupRemote(url=_URL, credential_ref=_CRED_REF)
    result = _runner.invoke(cli_app, ["sync", "status"])
    assert result.exit_code == 0, result.output
    assert "example.invalid" in result.output
    assert _CRED_REF in result.output
    assert _PUSH_SECRET not in result.output
    assert "none yet" in result.output


def test_status_reports_the_last_run(backup_cli: _StubBackupService) -> None:
    backup_cli.remote = BackupRemote(url=_URL)
    _runner.invoke(cli_app, ["sync", "push"])
    result = _runner.invoke(cli_app, ["sync", "status"])
    assert result.exit_code == 0, result.output
    assert "abc1234" in result.output


def test_status_without_a_remote_says_so(backup_cli: _StubBackupService) -> None:
    result = _runner.invoke(cli_app, ["sync", "status"])
    assert result.exit_code == 0, result.output
    assert "no backup remote configured" in result.output


def test_remote_set_can_name_the_push_credential(
    backup_cli: _StubBackupService,
) -> None:
    """A CLI-only user must be able to configure a private remote's token.

    The secret goes into the credential store separately (`coffer credentials
    set`); `set` records only the reference, so nothing secret reaches argv or
    the stored remote.
    """
    result = _runner.invoke(
        cli_app, ["sync", "remote", "set", _URL, "--credential-ref", "sync.TOK"]
    )

    assert result.exit_code == 0, result.output
    stored = backup_cli.remote
    assert stored is not None
    assert stored.credential_ref == "sync.TOK"


def test_a_named_credential_ref_replaces_the_one_already_stored(
    backup_cli: _StubBackupService,
) -> None:
    backup_cli.remote = BackupRemote(url=_URL, credential_ref=_CRED_REF)

    result = _runner.invoke(
        cli_app, ["sync", "remote", "set", _URL, "--credential-ref", "sync.OTHER"]
    )

    assert result.exit_code == 0, result.output
    stored = backup_cli.remote
    assert stored is not None
    assert stored.credential_ref == "sync.OTHER"

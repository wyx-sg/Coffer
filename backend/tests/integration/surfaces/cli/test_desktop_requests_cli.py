"""The command line's desktop requests and the end of ``coffer approval``,
against a real daemon.

Spec desktop-app "Serve the command line's desktop requests" and secret
"Answer a secret's approval only in the app". The shell is played by
:class:`FakeShell`, which does what ``desktop_requests.rs`` does — claim a
request, run the flow and say how it ended — with the person's answer chosen
by the test. The CLI's waits are the shell's ticks, so nothing here races.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli import _desktop
from coffer.surfaces.cli.main import app
from tests.support.boundary_daemon import (
    BoundaryDaemon,
    point_cli_at,
    prepare_home,
    running_daemon,
)

_runner = CliRunner()


class FakeShell:
    """The desktop shell, with the person's answer set by the test."""

    def __init__(self, d: BoundaryDaemon) -> None:
        self.d = d
        #: ``approve`` (the person writes the backup) or ``cancel``.
        self.answer = "approve"
        self.running = True
        #: The ``op`` of every request claimed.
        self.ops: list[str] = []
        #: Where the person picks to write a key backup.
        self.backup_dir: pathlib.Path | None = None
        self.result: dict[str, Any] | None = None

    def _backup(self) -> tuple[str, str | None]:
        """What ``secrets.rs`` does once the person passes the check in the
        dialog: the daemon writes the file, and the request ends with the path
        and fingerprint the daemon answered — or the dialog is closed."""
        if self.answer != "approve" or self.backup_dir is None:
            return "cancelled", "the backup dialog was closed without writing a backup"
        target = str(self.backup_dir)
        r = self.d.client.post(
            "/api/v1/secrets/presence/master-key-export",
            json={
                "directory": target,
                "passphrase": "qa-cli-passphrase",
                **self.d.grant("export_master_key", target),
            },
        )
        assert r.status_code == 200, r.text
        self.result = {"path": r.json()["path"], "fingerprint": r.json()["fingerprint"]}
        return "done", f"the backup was written to {r.json()['path']}"

    def tick(self, _seconds: float = 0) -> None:
        if not self.running:
            return
        r = self.d.client.post("/api/v1/desktop/requests/claim")
        if r.status_code == 204:
            return
        request = r.json()
        self.ops.append(request["op"])
        self.result = None
        status, message = self._handle(request)
        self.d.client.post(
            f"/api/v1/desktop/requests/{request['id']}/finish",
            json={"status": status, "message": message, "result": self.result},
        )

    def _handle(self, request: dict[str, Any]) -> tuple[str, str | None]:
        if request["op"] == "export_master_key":
            return self._backup()
        if request["op"] == "import_master_key":
            return "done", "opened the master key import in the Coffer app"
        return "failed", f"this app does not know the request {request['op']!r}"


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        point_cli_at(d, monkeypatch)
        yield d


@pytest.fixture
def shell(daemon: BoundaryDaemon, monkeypatch: pytest.MonkeyPatch) -> FakeShell:
    fake = FakeShell(daemon)
    monkeypatch.setattr(_desktop, "sleep", fake.tick)
    monkeypatch.setattr(_desktop, "launcher", lambda: True)
    return fake


def coffer(*args: str, code: int = 0) -> Any:
    result = _runner.invoke(app, list(args))
    assert result.exit_code == code, (args, result.output)
    return result


def _pending(d: BoundaryDaemon, name: str) -> dict[str, Any]:
    """One pending approval: a second server citing a secret the first holds."""
    d.store("secret/shared", "value-1")
    d.register_stdio("first", "true", {"TOKEN": "secret/shared"})
    for approval in d.pending():
        d.approve(approval["id"])
    d.register_stdio(name, "true", {"TOKEN": "secret/shared"})
    [approval] = [a for a in d.pending() if a["destination_label"] == name]
    return approval


@pytest.mark.acceptance(
    spec="secret", scenario="the command line answers no approval and says who does"
)
def test_the_command_line_answers_no_approval(daemon: BoundaryDaemon, shell: FakeShell) -> None:
    approval = _pending(daemon, "second")
    for verb in ("list", "approve", "reject", "ask-again"):
        result = _runner.invoke(app, ["approval", verb, approval["id"]])
        assert result.exit_code == 2, (verb, result.output)
    assert (
        daemon.client.get(f"/api/v1/secrets/approvals/{approval['id']}").json()["status"]
        == "pending"
    )
    assert shell.ops == []


@pytest.mark.acceptance(spec="secret", scenario="a stale or replayed grant approves nothing")
def test_a_stale_or_replayed_grant_approves_nothing(daemon: BoundaryDaemon) -> None:
    fresh = _pending(daemon, "second")
    grant = daemon.grant("approve", f"{fresh['id']}@stale-fingerprint")
    r = daemon.client.post(
        f"/api/v1/secrets/approvals/{fresh['id']}/approve",
        json={**grant, "fingerprint": "stale-fingerprint"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "APPROVAL_TARGET_CHANGED"
    good = daemon.grant("approve", f"{fresh['id']}@{fresh['target_fingerprint']}")
    body = {**good, "fingerprint": fresh["target_fingerprint"]}
    assert daemon.client.post(
        f"/api/v1/secrets/approvals/{fresh['id']}/approve", json=body
    ).is_success
    replay = daemon.client.post(f"/api/v1/secrets/approvals/{fresh['id']}/approve", json=body)
    assert replay.status_code == 403 and replay.json()["error"]["code"] == "PRESENCE_GRANT_INVALID"


@pytest.mark.acceptance(
    spec="secret",
    scenario="a key backup started from the command line reports what was written",
)
def test_a_key_backup_reports_the_file_written(
    daemon: BoundaryDaemon, shell: FakeShell, tmp_path: pathlib.Path
) -> None:
    shell.backup_dir = tmp_path / "qa-cli-backup"
    shell.backup_dir.mkdir()
    backup = coffer("secret", "backup-key", "--json")
    answer = json.loads(backup.stdout)
    written = shell.backup_dir / "coffer-master-key.cfk"
    assert answer["status"] == "done" and answer["result"]["path"] == str(written)
    assert written.is_file()
    assert set(answer["result"]) == {"path", "fingerprint"}
    assert "qa-cli-passphrase" not in backup.output
    # Closing the dialog writes nothing, and the command does not say otherwise.
    shell.answer = "cancel"
    closed = coffer("secret", "backup-key", code=11)
    assert "written" not in closed.output.replace("without writing", "")
    assert sorted(p.name for p in shell.backup_dir.iterdir()) == ["coffer-master-key.cfk"]


def test_an_app_that_reports_done_without_a_file_is_not_a_backup(
    daemon: BoundaryDaemon, shell: FakeShell, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shell, "_backup", lambda: ("done", "opened the backup"))
    result = coffer("secret", "backup-key", code=11)
    assert "did not report a written backup" in result.output


def test_key_import_opens_in_the_app(daemon: BoundaryDaemon, shell: FakeShell) -> None:
    imported = coffer("secret", "import-key", "--json")
    assert shell.ops == ["import_master_key"]
    assert json.loads(imported.output)["status"] == "done"

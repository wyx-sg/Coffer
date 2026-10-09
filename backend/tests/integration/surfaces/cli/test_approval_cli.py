"""``coffer approval`` with the desktop shell's presence check, against a real daemon.

Spec secret "Approve from the command line with the person's own presence
check" and desktop-app "Serve the command line's desktop requests". The shell
is played by :class:`FakeShell`, which does what ``desktop_requests.rs`` does
— claim a request, read each approval from the daemon, refuse a target that
moved, sign a grant pinned to the target and call the approve route — with the
person's answer chosen by the test. The CLI's waits are the shell's ticks, so
nothing here races.
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
        #: ``approve`` (Touch ID passes), ``cancel`` or ``fail``.
        self.answer = "approve"
        self.running = True
        self.prompts: list[str] = []
        #: The ``op`` of every request claimed.
        self.ops: list[str] = []
        #: Run between the claim and the prompt (to move a target meanwhile).
        self.before_prompt: Any = None
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
        if self.before_prompt is not None:
            self.before_prompt()
        for pin in request["approvals"]:
            approval = self.d.client.get(f"/api/v1/secrets/approvals/{pin['id']}").json()
            if (
                approval["status"] != "pending"
                or approval["target_fingerprint"] != pin["fingerprint"]
            ):
                return "failed", "the approval now names another target"
            self.prompts.append(approval["description"])
            if self.answer == "cancel":
                return "cancelled", "cancelled"
            if self.answer == "fail":
                return "failed", "the presence check failed"
            target = f"{pin['id']}@{pin['fingerprint']}"
            grant = self.d.grant("approve", target)
            r = self.d.client.post(
                f"/api/v1/secrets/approvals/{pin['id']}/approve",
                json={**grant, "fingerprint": pin["fingerprint"]},
            )
            if r.status_code != 200:
                return "failed", r.json()["error"]["message"]
        return "done", None


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


def _pending(d: BoundaryDaemon, *names: str) -> list[str]:
    """One pending approval per server, each citing a secret another server holds."""
    d.store("secret/shared", "value-1")
    d.register_stdio("first", "true", {"TOKEN": "secret/shared"})
    for approval in d.pending():
        d.approve(approval["id"])
    ids = []
    for name in names:
        d.register_stdio(name, "true", {"TOKEN": "secret/shared"})
        [approval] = [a for a in d.pending() if a["destination_label"] == name]
        ids.append(approval["id"])
    return ids


def coffer(*args: str, code: int = 0) -> Any:
    result = _runner.invoke(app, list(args))
    assert result.exit_code == code, (args, result.output)
    return result


def _status(d: BoundaryDaemon, approval_id: str) -> str:
    return str(d.client.get(f"/api/v1/secrets/approvals/{approval_id}").json()["status"])


@pytest.mark.acceptance(
    spec="secret", scenario="a command line approval asks the person and applies after the check"
)
@pytest.mark.acceptance(spec="desktop-app", scenario="the shell serves a command line approval")
def test_a_command_line_approval_asks_the_person(daemon: BoundaryDaemon, shell: FakeShell) -> None:
    [approval] = _pending(daemon, "second")
    listed = json.loads(coffer("approval", "list", "--json").stdout)
    assert [a["id"] for a in listed["approvals"]] == [approval]
    out = json.loads(coffer("approval", "approve", approval, "--json").stdout)
    assert out["request"]["status"] == "done"
    assert out["approvals"] == [
        {"id": approval, "status": "approved", "description": out["approvals"][0]["description"]}
    ]
    assert len(shell.prompts) == 1 and "second" in shell.prompts[0]
    assert _status(daemon, approval) == "approved"


@pytest.mark.acceptance(
    spec="secret", scenario="a check that is not confirmed leaves the approval pending"
)
@pytest.mark.parametrize("answer", ["cancel", "fail"])
def test_a_check_not_confirmed_leaves_it_pending(
    daemon: BoundaryDaemon, shell: FakeShell, answer: str
) -> None:
    [approval] = _pending(daemon, "second")
    shell.answer = answer
    out = coffer("approval", "approve", approval, code=11)
    assert "not confirmed" in out.output
    assert _status(daemon, approval) == "pending"


def test_a_check_nobody_answers_times_out_pending(daemon: BoundaryDaemon, shell: FakeShell) -> None:
    [approval] = _pending(daemon, "second")
    shell.tick()  # the shell is running...
    shell.running = False  # ...and then nobody answers.
    coffer("approval", "approve", approval, "--timeout", "0", code=11)
    assert _status(daemon, approval) == "pending"


@pytest.mark.acceptance(
    spec="secret", scenario="a moved target or a replayed grant approves nothing"
)
def test_a_moved_target_or_a_replayed_grant_approves_nothing(
    daemon: BoundaryDaemon, shell: FakeShell
) -> None:
    [approval] = _pending(daemon, "second")
    uid = next(
        r["uid"]
        for r in daemon.client.get("/api/v1/resources").json()["resources"]
        if r["name"] == "second"
    )

    def move() -> None:
        r = daemon.client.patch(
            f"/api/v1/resources/{uid}",
            json={
                "config": {
                    "transport": {
                        "type": "stdio",
                        "command": "other",
                        "secret_refs": {"TOKEN": "secret/shared"},
                    }
                }
            },
        )
        assert r.status_code == 200, r.text

    shell.before_prompt = move
    coffer("approval", "approve", approval, code=11)
    assert _status(daemon, approval) == "superseded"
    # A pinned grant for the old target is refused by the daemon too.
    [fresh] = [a for a in daemon.pending() if a["destination_label"] == "second"]
    grant = daemon.grant("approve", f"{fresh['id']}@stale-fingerprint")
    r = daemon.client.post(
        f"/api/v1/secrets/approvals/{fresh['id']}/approve",
        json={**grant, "fingerprint": "stale-fingerprint"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "APPROVAL_TARGET_CHANGED"
    # And a grant is good once: replaying it approves nothing.
    good = daemon.grant("approve", f"{fresh['id']}@{fresh['target_fingerprint']}")
    body = {**good, "fingerprint": fresh["target_fingerprint"]}
    assert daemon.client.post(
        f"/api/v1/secrets/approvals/{fresh['id']}/approve", json=body
    ).is_success
    replay = daemon.client.post(f"/api/v1/secrets/approvals/{fresh['id']}/approve", json=body)
    assert replay.status_code == 403 and replay.json()["error"]["code"] == "PRESENCE_GRANT_INVALID"


@pytest.mark.acceptance(
    spec="secret", scenario="the desktop app is started, or the command says it is unavailable"
)
def test_the_app_is_started_or_reported_unavailable(
    daemon: BoundaryDaemon, shell: FakeShell, monkeypatch: pytest.MonkeyPatch
) -> None:
    [first, second] = _pending(daemon, "second", "third")
    started: list[bool] = []
    monkeypatch.setattr(_desktop, "launcher", lambda: started.append(True) or True)
    coffer("approval", "approve", first)
    assert started == [True]
    shell.running = False
    monkeypatch.setattr(_desktop, "launcher", lambda: False)
    monkeypatch.setattr(_desktop, "LAUNCH_WAIT_SECONDS", 0.0)
    # The shell's last poll has gone stale.
    from coffer.surfaces.http import desktop_request_routes

    desktop_request_routes.get_desktop_requests()._shell_seen_at = None
    out = json.loads(coffer("approval", "approve", second, "--json", code=12).stderr)
    assert out["error"]["code"] == "CLI_APP_UNAVAILABLE"
    assert _status(daemon, second) == "pending"


@pytest.mark.acceptance(spec="secret", scenario="no flag skips the presence check")
def test_no_flag_skips_the_presence_check(daemon: BoundaryDaemon, shell: FakeShell) -> None:
    [approval] = _pending(daemon, "second")
    for flag in ("--yes", "--force"):
        coffer("approval", "approve", approval, flag, code=2)
    assert _status(daemon, approval) == "pending" and shell.prompts == []


@pytest.mark.acceptance(
    spec="secret", scenario="several approvals cover exactly the ones named and still waiting"
)
def test_several_approvals_cover_exactly_those_named(
    daemon: BoundaryDaemon, shell: FakeShell
) -> None:
    first, second, third = _pending(daemon, "second", "third", "fourth")
    coffer("approval", "approve", first, second)
    assert [_status(daemon, i) for i in (first, second, third)] == [
        "approved",
        "approved",
        "pending",
    ]
    # One no longer waiting is refused up front, and nothing is asked.
    out = coffer("approval", "approve", first, third, code=5)
    assert "already approved" in out.output
    assert _status(daemon, third) == "pending"


def test_reject_needs_no_presence(daemon: BoundaryDaemon, shell: FakeShell) -> None:
    first, second = _pending(daemon, "second", "third")
    coffer("approval", "reject", first, second)
    assert {_status(daemon, first), _status(daemon, second)} == {"rejected"}
    assert shell.prompts == []


def test_ask_again_puts_a_refused_request_back_without_presence(
    daemon: BoundaryDaemon, shell: FakeShell
) -> None:
    (refused,) = _pending(daemon, "second")
    coffer("approval", "reject", refused)
    out = coffer("approval", "ask-again", refused, "--json")
    [asked] = json.loads(out.output)["approvals"]
    assert _status(daemon, refused) == "superseded"
    assert _status(daemon, asked["id"]) == "pending"
    assert shell.prompts == []
    coffer("approval", "ask-again", asked["id"], code=5)


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

"""``/api/v1/clis`` over the real app: what skills declare, how each command
is checked, the Homebrew install and the attention items (spec skill-manager,
the required-command requirements; spec resource-framework "Report what needs
a person across every kind").

The probe and Homebrew are fakes injected at the composition root's seam
(``cli_wiring``) — nothing here runs a real ``brew``. The two tests about the
real ``PATH`` lookup and the discarded login output run the real
``CommandProbe`` against scripts this test writes into ``tmp_path``.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import threading
from collections.abc import Iterator

import pytest

from coffer.infrastructure.platform.user_path import UserPath
from coffer.infrastructure.skill.command_probe import CommandProbe
from tests.support.cli_requirements import (
    FAKE_BREW,
    FakeCommand,
    FakeCommandProbe,
    FakeInstaller,
)

from ._cli_requirements_app import CliDaemon, boot_cli_daemon
from ._real_app import audit

_GH = '  - command: gh\n    min_version: "{min}"\n    brew: gh\n'


@pytest.fixture
def probe() -> FakeCommandProbe:
    return FakeCommandProbe()


@pytest.fixture
def installer() -> FakeInstaller:
    return FakeInstaller()


@pytest.fixture
def daemon(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    probe: FakeCommandProbe,
    installer: FakeInstaller,
) -> Iterator[CliDaemon]:
    yield from boot_cli_daemon(tmp_path, monkeypatch, probe=probe, installer=installer)


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a skill's requires list is read from its frontmatter"
)
def test_requires_list_is_read(daemon: CliDaemon, probe: FakeCommandProbe) -> None:
    probe.commands["gh"] = FakeCommand("2.45.0", logged_in=True)
    probe.commands["jq"] = FakeCommand("1.7.1")
    uid = daemon.add_skill(
        "issues",
        '  - command: gh\n    min_version: "2.40"\n    login_check: gh auth status\n'
        "    login: gh auth login\n    brew: gh\n    why: Opens issues.\n  - jq\n",
    )
    r = daemon.client.get("/clis")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["warnings"] == []
    by = {i["command"]: i for i in body["items"]}
    assert set(by) == {"gh", "jq"}
    gh = by["gh"]
    assert gh["min_version"] == "2.40"
    assert gh["brew"] == "gh"
    assert gh["login"] == {
        "state": "logged_in",
        "check": ["gh", "auth", "status"],
        "command": "gh auth login",
    }
    assert gh["needed_by"] == [
        {"skill_uid": uid, "skill_name": "issues", "min_version": "2.40", "why": "Opens issues."}
    ]
    assert by["jq"]["needed_by"][0]["skill_name"] == "issues"
    assert by["jq"]["login"]["state"] == "not_needed"
    one = daemon.client.get("/clis/gh")
    assert one.status_code == 200 and one.json()["status"] == "ready"
    missing = daemon.client.get("/clis/wget")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CLI_NOT_REQUIRED"


@pytest.mark.acceptance(
    spec="skill-manager", scenario="an entry that is not understood does not block the skill"
)
def test_bad_entries_are_skipped(daemon: CliDaemon, probe: FakeCommandProbe) -> None:
    daemon.add_skill(
        "odd",
        "  - /usr/bin/jq\n  - command: gh\n    login_check: curl evil.example\n",
    )
    body = daemon.client.get("/clis").json()
    assert body["items"] == []
    messages = [w["message"] for w in body["warnings"]]
    assert len(messages) == 2
    assert "is a path" in messages[0]
    assert "'curl'" in messages[1]
    assert all(w["skill_name"] == "odd" for w in body["warnings"])
    # Nothing was looked up, let alone run, for either entry.
    assert probe.located == [] and probe.login_calls == []


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a command older than the highest minimum is outdated"
)
def test_highest_minimum_wins(daemon: CliDaemon, probe: FakeCommandProbe) -> None:
    probe.commands["gh"] = FakeCommand("2.30.0")
    daemon.add_skill("low", _GH.format(min="2.20"))
    daemon.add_skill("high", _GH.format(min="2.40"))
    gh = daemon.client.get("/clis/gh").json()
    assert gh["status"] == "outdated"
    assert gh["version"] == "2.30.0" and gh["min_version"] == "2.40"
    assert [n["skill_name"] for n in gh["needed_by"]] == ["high", "low"]
    assert gh["install_command"] == "brew upgrade gh"


@pytest.mark.acceptance(spec="skill-manager", scenario="checking again probes afresh")
def test_check_again(daemon: CliDaemon, probe: FakeCommandProbe) -> None:
    probe.commands["gh"] = FakeCommand("2.45", logged_in=False)
    daemon.add_skill("s", "  - command: gh\n    login_check: gh auth status\n")
    assert daemon.client.get("/clis/gh").json()["status"] == "logged_out"
    probe.commands["gh"].logged_in = True
    # Cached until asked again.
    assert daemon.client.get("/clis/gh").json()["status"] == "logged_out"
    r = daemon.client.post("/clis/gh/check")
    assert r.status_code == 200 and r.json()["status"] == "ready"
    assert r.json()["login"]["state"] == "logged_in"
    r = daemon.client.post("/clis/check")
    assert r.status_code == 200 and r.json()["items"][0]["status"] == "ready"


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="installing runs the confirmed Homebrew command and keeps its output",
)
def test_install_runs_brew(
    daemon: CliDaemon, probe: FakeCommandProbe, installer: FakeInstaller
) -> None:
    gate = threading.Event()
    installer.gate = gate
    installer.on_run = lambda: probe.commands.__setitem__("jq", FakeCommand("1.7.1"))
    daemon.add_skill("s", "  - command: jq\n    brew: jq\n")
    assert daemon.client.get("/clis/jq").json()["install_command"] == "brew install jq"
    r = daemon.client.post("/clis/jq/install", json={"formula": "jq"})
    assert r.status_code == 202, r.text
    assert r.json()["argv"] == [FAKE_BREW, "install", "jq"]
    assert "sudo" not in r.json()["argv"]
    # Served while it runs.
    running = daemon.client.get("/clis/jq/install").json()
    assert running["state"] == "running"
    again = daemon.client.post("/clis/jq/install", json={"formula": "jq"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "CLI_INSTALL_RUNNING"
    gate.set()
    done = daemon.wait_install("jq")
    assert done["state"] == "succeeded" and done["exit_code"] == 0
    assert done["lines"] == list(installer.lines)
    assert installer.runs == [(FAKE_BREW, "install", "jq")]
    started = audit(daemon.client, "cli_install_started")
    finished = audit(daemon.client, "cli_install_finished")
    assert started[0]["details"]["argv"] == [FAKE_BREW, "install", "jq"]
    assert finished[0]["details"]["exit_code"] == 0
    assert finished[0]["details"]["output_tail"] == list(installer.lines)
    # Checked again when it ended.
    jq = daemon.client.get("/clis/jq").json()
    assert jq["status"] == "ready" and jq["version"] == "1.7.1"
    assert jq["install_state"] == "succeeded"


@pytest.mark.acceptance(
    spec="skill-manager", scenario="an install naming another formula is refused"
)
def test_install_refusals(daemon: CliDaemon, installer: FakeInstaller) -> None:
    daemon.add_skill("s", "  - command: jq\n    brew: jq\n  - fd\n")
    r = daemon.client.post("/clis/jq/install", json={"formula": "wget"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "CLI_FORMULA_MISMATCH"
    r = daemon.client.post("/clis/fd/install", json={"formula": "fd"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CLI_NOT_INSTALLABLE"
    assert r.json()["error"]["details"]["reason"] == "no_formula"
    installer.brew = None
    r = daemon.client.post("/clis/jq/install", json={"formula": "jq"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "HOMEBREW_NOT_FOUND"
    assert installer.runs == []
    assert audit(daemon.client, "cli_install_started") == []
    r = daemon.client.get("/clis/jq/install")
    assert r.status_code == 404 and r.json()["error"]["code"] == "CLI_INSTALL_NOT_FOUND"


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a required command that needs attention is listed"
)
def test_attention_lists_the_outdated_command(daemon: CliDaemon, probe: FakeCommandProbe) -> None:
    probe.commands["gh"] = FakeCommand("2.30")
    daemon.add_skill("s", _GH.format(min="2.40"))
    items = [i for i in daemon.client.get("/attention").json()["items"] if i["kind"] == "cli"]
    assert len(items) == 1
    item = items[0]
    assert (item["uid"], item["reason_code"], item["severity"]) == ("gh", "cli_outdated", "warning")
    assert item["action"] == {
        "verb": "check",
        "method": "POST",
        "path": "/api/v1/clis/gh/check",
        "body": None,
    }
    probe.commands["gh"] = FakeCommand("2.41")
    assert daemon.client.post(item["action"]["path"].removeprefix("/api/v1")).status_code == 200
    items = [i for i in daemon.client.get("/attention").json()["items"] if i["kind"] == "cli"]
    assert items == []


# ---------- the real probe, on a PATH this test lays out ----------


def _script(bin_dir: pathlib.Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def shell_bin(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """A directory only the login shell's ``PATH`` lists — not the daemon's."""
    bin_dir = tmp_path / "shell-bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    return bin_dir


def _real_probe(bin_dir: pathlib.Path) -> CommandProbe:
    shell = str(bin_dir)
    return CommandProbe(user_path=UserPath(shell_path=lambda: shell))


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="a required command is found with its version on the agent's path",
)
def test_found_on_the_login_shell_path(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, shell_bin: pathlib.Path
) -> None:
    _script(shell_bin, "uv", 'echo "uv 0.4.18 (Homebrew)"')
    assert str(shell_bin) not in os.environ["PATH"].split(os.pathsep)
    for d in boot_cli_daemon(tmp_path, monkeypatch, probe=_real_probe(shell_bin)):
        d.add_skill("py", '  - command: uv\n    min_version: "0.4"\n')
        uv = d.client.get("/clis/uv").json()
        assert uv["status"] == "ready"
        assert uv["version"] == "0.4.18"
        assert uv["path"] == str((shell_bin / "uv").resolve())


_ACCOUNT = "octocat-secret-account-7f3a"


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="a failed login check reports not logged in without keeping its output",
)
def test_login_output_is_discarded(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    shell_bin: pathlib.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    _script(
        shell_bin,
        "gh",
        'if [ "$1" = "--version" ]; then echo "gh version 2.45.0"; exit 0; fi\n'
        f'echo "Logged in to github.com account {_ACCOUNT}"; echo "{_ACCOUNT}" >&2; exit 1',
    )
    for d in boot_cli_daemon(tmp_path, monkeypatch, probe=_real_probe(shell_bin)):
        d.add_skill(
            "issues",
            "  - command: gh\n    login_check: gh auth status\n    login: gh auth login\n",
        )
        responses = [
            d.client.get("/clis"),
            d.client.get("/clis/gh"),
            d.client.post("/clis/gh/check"),
            d.client.post("/clis/check"),
            d.client.get("/attention"),
            d.client.get("/audit"),
        ]
        gh = responses[1].json()
        assert gh["status"] == "logged_out" and gh["login"]["state"] == "logged_out"
        for r in responses:
            assert r.status_code == 200, r.text
            assert _ACCOUNT not in r.text
    assert _ACCOUNT not in caplog.text
    for log in (tmp_path / "logs").rglob("*"):
        if log.is_file():
            assert _ACCOUNT not in log.read_text(encoding="utf-8", errors="replace")
    for db in tmp_path.glob("c.db*"):
        assert _ACCOUNT.encode() not in db.read_bytes()
    assert json.dumps(_ACCOUNT) not in caplog.text

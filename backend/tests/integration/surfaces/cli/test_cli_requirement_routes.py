"""``/api/v1/clis`` over the real app: what skills declare, how each command
is checked, the hand-off prompt and the attention items (spec skill-manager,
the required-command requirements; spec resource-framework "Report what needs
a person across every kind").

The probe is a fake injected at the composition root's seam (``cli_wiring``).
The two tests about the real ``PATH`` lookup and the discarded login output run
the real ``CommandProbe`` against scripts this test writes into ``tmp_path``.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
from collections.abc import Iterator

import pytest

from coffer.domain.skill.cli_status import COFFER_NEEDS
from coffer.infrastructure.platform.user_path import UserPath
from coffer.infrastructure.skill.command_probe import CommandProbe
from tests.support.cli_requirements import FAKE_MACHINE, FakeCommand, FakeCommandProbe

from ._cli_requirements_app import CliDaemon, boot_cli_daemon

_GH = '  - command: gh\n    min_version: "{min}"\n'


@pytest.fixture
def probe() -> FakeCommandProbe:
    return FakeCommandProbe()


@pytest.fixture
def daemon(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    probe: FakeCommandProbe,
) -> Iterator[CliDaemon]:
    yield from boot_cli_daemon(tmp_path, monkeypatch, probe=probe)


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a skill's requires list is read from its frontmatter"
)
def test_requires_list_is_read(daemon: CliDaemon, probe: FakeCommandProbe) -> None:
    probe.commands["gh"] = FakeCommand("2.45.0", logged_in=True)
    probe.commands["jq"] = FakeCommand("1.7.1")
    uid = daemon.add_skill(
        "issues",
        '  - command: gh\n    min_version: "2.40"\n    login_check: gh auth status\n'
        "    login: gh auth login\n    why: Opens issues.\n  - jq\n",
    )
    # A read never runs a login check; an explicit Check does.
    assert daemon.client.get("/clis").json()["items"][0]["login"]["state"] in (None, "not_needed")
    assert probe.login_calls == []
    r = daemon.client.post("/clis/check")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["warnings"] == []
    by = {i["command"]: i for i in body["items"]}
    assert set(by) == {"gh", "jq"}
    gh = by["gh"]
    assert gh["min_version"] == "2.40"
    assert gh["handoff"] is None
    assert gh["login"] == {
        "state": "logged_in",
        "check": ["gh", "auth", "status"],
        "command": "gh auth login",
    }
    assert gh["needed_by"] == [
        {
            "skill_uid": uid,
            "skill_name": "issues",
            "min_version": "2.40",
            "why": "Opens issues.",
            "profiles": [],
        }
    ]
    assert by["jq"]["needed_by"][0]["skill_name"] == "issues"
    assert by["jq"]["login"]["state"] == "not_needed"
    one = daemon.client.get("/clis/gh")
    assert one.status_code == 200 and one.json()["status"] == "ready"
    missing = daemon.client.get("/clis/wget")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CLI_NOT_KNOWN"


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
    prompt = gh["handoff"]["prompt"]
    assert prompt.startswith("Please update the command-line tool `gh`")
    assert "Installed: 2.30.0 at /fake/bin/gh; version 2.40 or newer is needed." in prompt


@pytest.mark.acceptance(spec="skill-manager", scenario="checking again probes afresh")
def test_check_again(daemon: CliDaemon, probe: FakeCommandProbe) -> None:
    probe.commands["gh"] = FakeCommand("2.45", logged_in=False)
    daemon.add_skill("s", "  - command: gh\n    login_check: gh auth status\n")
    assert daemon.client.post("/clis/gh/check").json()["status"] == "logged_out"
    probe.commands["gh"].logged_in = True
    # Cached until asked again.
    assert daemon.client.get("/clis/gh").json()["status"] == "logged_out"
    r = daemon.client.post("/clis/gh/check")
    assert r.status_code == 200 and r.json()["status"] == "ready"
    assert r.json()["login"]["state"] == "logged_in"
    r = daemon.client.post("/clis/check")
    assert r.status_code == 200 and r.json()["items"][0]["status"] == "ready"


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a missing command carries an install prompt for an agent"
)
def test_a_missing_command_carries_an_install_prompt(daemon: CliDaemon) -> None:
    daemon.add_skill("issues", _GH.format(min="2.40"))
    daemon.add_skill("triage", "  - command: gh\n    title: GitHub CLI\n")
    gh = daemon.client.get("/clis/gh").json()
    assert gh["status"] == "missing"
    assert gh["handoff"]["prompt"] == (
        "Please install the command-line tool `gh` (GitHub CLI) on this machine.\n"
        "\n"
        "- Needed by the Coffer skills: issues (version 2.40 or newer), triage.\n"
        f"- This machine: {FAKE_MACHINE}.\n"
        "\n"
        "Choose the right install method for this machine.\n"
        "When you are done, run `gh --version` to confirm it works.\n"
        "Check with me before running anything that needs sudo or changes system settings.\n"
        "If a login is needed, tell me how and I will log in myself; do not handle my credentials."
    )
    # The list carries the same prompt, and there is nothing that installs.
    listed = daemon.client.get("/clis").json()["items"][0]
    assert listed["handoff"] == gh["handoff"]
    assert daemon.client.post("/clis/gh/install", json={"formula": "gh"}).status_code in (404, 405)


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="a command that is not logged in carries a prompt that asks only for help logging in",
)
def test_a_logged_out_command_asks_only_for_login_help(
    daemon: CliDaemon, probe: FakeCommandProbe
) -> None:
    probe.commands["gh"] = FakeCommand("2.45.0", logged_in=False)
    daemon.add_skill(
        "issues", "  - command: gh\n    login_check: gh auth status\n    login: gh auth login\n"
    )
    prompt = daemon.client.post("/clis/gh/check").json()["handoff"]["prompt"]
    assert prompt.startswith("Please help me log in to the command-line tool `gh`.")
    assert "`gh auth status` says I am not logged in" in prompt
    assert "The skills suggest logging in with `gh auth login`." in prompt
    assert "I will run it and enter anything it asks for myself." in prompt
    assert "do not handle my credentials" in prompt
    assert "Please install" not in prompt and "install method" not in prompt


@pytest.mark.acceptance(spec="skill-manager", scenario="a ready command carries no prompt")
def test_a_ready_command_carries_no_prompt(daemon: CliDaemon, probe: FakeCommandProbe) -> None:
    probe.commands["jq"] = FakeCommand("1.7.1")
    daemon.add_skill("data", "  - jq\n")
    jq = daemon.client.get("/clis/jq").json()
    assert (jq["status"], jq["handoff"]) == ("ready", None)


def test_a_legacy_brew_field_is_ignored_with_a_warning(daemon: CliDaemon) -> None:
    daemon.add_skill("old", "  - command: jq\n    brew: jq\n")
    body = daemon.client.get("/clis").json()
    assert [i["command"] for i in body["items"]] == ["jq"]
    assert [w["message"] for w in body["warnings"]] == [
        "requires jq: unknown field(s) brew ignored"
    ]


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
            d.client.post("/clis/gh/check"),
            d.client.get("/clis/gh"),
            d.client.post("/clis/check"),
            d.client.get("/attention"),
            d.client.get("/audit"),
        ]
        gh = responses[2].json()
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


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a CLI page lists the MCP servers started with the command"
)
def test_a_stdio_servers_launcher_is_listed_with_the_server(daemon: CliDaemon) -> None:
    config = {"transport": {"type": "stdio", "command": "uvx", "args": ["mcp-server-duckdb"]}}
    made = daemon.client.post(
        "/resources", json={"kind": "mcp_server", "name": "duckdb", "config": config}
    )
    assert made.status_code == 201, made.text
    daemon.add_skill("data-profiling", '  - command: uv\n    min_version: "0.4"\n')
    r = daemon.client.get("/clis/uv")
    assert r.status_code == 200, r.text
    uv = r.json()
    assert uv["status"] == "missing"
    assert [n["skill_name"] for n in uv["needed_by"]] == ["data-profiling"]
    assert uv["needed_by_servers"] == [
        {"server_uid": made.json()["uid"], "server_name": "duckdb", "launcher": "uvx"}
    ]
    prompt = uv["handoff"]["prompt"]
    assert "duckdb (started with `uvx`)" in prompt and "data-profiling" in prompt
    assert f"This machine: {FAKE_MACHINE}." in prompt


@pytest.mark.acceptance(spec="skill-manager", scenario="git is listed as needed by Coffer itself")
def test_git_is_needed_by_coffer(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, probe: FakeCommandProbe
) -> None:
    for daemon in boot_cli_daemon(tmp_path, monkeypatch, probe=probe, coffer_needs=COFFER_NEEDS):
        git = daemon.client.get("/clis/git").json()
        assert git["status"] == "missing"
        assert git["title"] == "Git"
        assert git["needed_by_coffer"] == ["vault_history", "sync"]
        assert git["needed_by"] == [] and git["needed_by_servers"] == []
        assert (
            "Coffer itself uses it to keep the vault's history and to sync the vault."
            in (git["handoff"]["prompt"])
        )
        # Overview carries one CLIs item for it, saying what Coffer can't do.
        items = daemon.client.get("/attention").json()["items"]
        (item,) = [i for i in items if i["kind"] == "cli"]
        assert item["uid"] == "git" and item["reason_code"] == "cli_missing"
        assert item["severity"] == "error"
        assert item["reason"] == (
            "git is not on the agent's PATH; Coffer needs it to keep the vault's history "
            "and to sync the vault."
        )
        assert item["handoff"] is not None
        probe.commands["git"] = FakeCommand("2.50.1")
        ready = daemon.client.post("/clis/git/check").json()
        assert ready["status"] == "ready" and ready["handoff"] is None
        items = daemon.client.get("/attention").json()["items"]
        assert not [i for i in items if i["kind"] == "cli"]

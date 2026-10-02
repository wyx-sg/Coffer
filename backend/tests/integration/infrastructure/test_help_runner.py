"""The help runner against real executables the test lays out in ``tmp_path``
(spec skill-manager "Show a command-line tool's full interface"): what it
runs, with what environment, and where it stops."""

from __future__ import annotations

import os
import pathlib
import stat

import pytest

from coffer.infrastructure.skill.help_runner import HelpRefused, HelpRunner, help_argv


def _script(folder: pathlib.Path, name: str, body: str) -> str:
    path = folder / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def _runner(timeout: float = 5.0, max_output: int = 256 * 1024) -> HelpRunner:
    return HelpRunner(user_path=lambda: "/usr/bin:/bin", timeout=timeout, max_output=max_output)


def test_runs_argv_with_only_the_help_flag(tmp_path: pathlib.Path) -> None:
    log = tmp_path / "argv.log"
    tool = _script(tmp_path, "t", f'echo "$@" > {log}; echo "Usage: t"')
    out = _runner().run(tool, ["commit"], "--help")
    assert out.text.strip() == "Usage: t" and not out.timed_out and out.error is None
    assert log.read_text().strip() == "commit --help"
    _runner().run(tool, ["a", "b"], "-h")
    assert log.read_text().strip() == "a b -h"
    _runner().run(tool, ["x"], "help")
    assert log.read_text().strip() == "help x"


@pytest.mark.parametrize(
    ("subs", "flag"),
    [
        ([], "--version"),
        ([], "--help; touch pwned"),
        (["--force"], "--help"),
        (["a b"], "--help"),
        (["a;b"], "--help"),
        (["$(id)"], "--help"),
        (["../x"], "--help"),
        ([""], "--help"),
    ],
)
def test_anything_but_a_help_request_is_refused(subs: list[str], flag: str) -> None:
    with pytest.raises(HelpRefused):
        help_argv("/bin/true", subs, flag)


def test_a_relative_path_is_refused() -> None:
    with pytest.raises(HelpRefused):
        help_argv("tool", [], "--help")


def test_the_environment_is_built_from_nothing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    monkeypatch.setenv("COFFER_API_TOKEN", "coffer-secret")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")
    tool = _script(tmp_path, "t", 'env; echo "home=$HOME"')
    text = _runner().run(tool, [], "--help").text
    assert "ghp_secret" not in text and "coffer-secret" not in text and "agent.sock" not in text
    names = {line.split("=", 1)[0] for line in text.splitlines() if "=" in line}
    assert names - {"PWD", "SHLVL", "_", "OLDPWD", "home"} <= {
        "PATH",
        "HOME",
        "LANG",
        "NO_COLOR",
        "TERM",
        "COLUMNS",
    }
    home = next(line for line in text.splitlines() if line.startswith("home="))[5:]
    # a throw-away folder: not the person's home, and gone afterwards
    assert home != str(pathlib.Path.home()) and not os.path.exists(home)


def test_stdin_is_closed(tmp_path: pathlib.Path) -> None:
    tool = _script(tmp_path, "t", 'if read line; then echo "got"; else echo "eof"; fi')
    assert _runner().run(tool, [], "--help").text.strip() == "eof"


def test_output_is_capped(tmp_path: pathlib.Path) -> None:
    tool = _script(tmp_path, "t", "yes 'a line of help' | head -c 2000000")
    out = _runner(max_output=4096).run(tool, [], "--help")
    assert out.truncated and len(out.text) == 4096


def test_a_tool_that_never_returns_is_killed_at_the_timeout(tmp_path: pathlib.Path) -> None:
    tool = _script(tmp_path, "t", "echo started; sleep 30")
    # Generous: on a loaded machine a shell script can take a while to print its first line.
    out = _runner(timeout=3.0).run(tool, [], "--help")
    assert out.timed_out and out.text.strip() == "started"


def test_a_file_that_cannot_run_reports_why(tmp_path: pathlib.Path) -> None:
    plain = tmp_path / "plain"
    plain.write_text("not executable", encoding="utf-8")
    out = _runner().run(str(plain), [], "--help")
    assert out.text == "" and out.error is not None

"""The two machine adapters of the required-command check, against scripts
this test writes — a stand-in ``brew`` among them, never the real one."""

from __future__ import annotations

import pathlib

from coffer.infrastructure.platform.user_path import UserPath
from coffer.infrastructure.skill.command_probe import CommandProbe
from coffer.infrastructure.skill.homebrew import HomebrewInstaller


def _script(bin_dir: pathlib.Path, name: str, body: str) -> pathlib.Path:
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _path(bin_dir: pathlib.Path) -> UserPath:
    shell = str(bin_dir)
    return UserPath(shell_path=lambda: shell)


def test_probe_reads_version_and_login_exit(tmp_path: pathlib.Path) -> None:
    gh = _script(
        tmp_path,
        "gh",
        'case "$1" in --version) echo "gh version 2.45.0";; auth) exit "$2";; esac',
    )
    probe = CommandProbe(user_path=_path(tmp_path))
    assert probe.locate("gh") == str(gh.resolve())
    assert probe.locate("no-such-command-xyz") is None
    assert probe.version(str(gh)) == "2.45.0"
    assert probe.login_ok([str(gh), "auth", "0"]) is True
    assert probe.login_ok([str(gh), "auth", "1"]) is False


def test_a_login_check_past_its_timeout_is_unknown(tmp_path: pathlib.Path) -> None:
    slow = _script(tmp_path, "slow", "sleep 5")
    probe = CommandProbe(user_path=_path(tmp_path), login_timeout=0.2)
    assert probe.login_ok([str(slow), "status"]) is None


def test_installer_streams_merged_output_non_interactively(tmp_path: pathlib.Path) -> None:
    brew = _script(
        tmp_path,
        "brew",
        'echo "args $*"\n'
        'echo "auto_update=$HOMEBREW_NO_AUTO_UPDATE noninteractive=$NONINTERACTIVE"\n'
        'read line || echo "stdin closed"\n'
        'echo "to stderr" >&2\n'
        "exit 3",
    )
    installer = HomebrewInstaller(user_path=_path(tmp_path))
    assert installer.locate() == str(brew)
    lines: list[str] = []
    code = installer.run([str(brew), "install", "jq"], lines.append)
    assert code == 3
    assert lines == [
        "args install jq",
        "auto_update=1 noninteractive=1",
        "stdin closed",
        "to stderr",
    ]


def test_installer_stops_at_its_ceiling(tmp_path: pathlib.Path) -> None:
    brew = _script(tmp_path, "brew", "echo start\nsleep 5\necho never")
    installer = HomebrewInstaller(user_path=_path(tmp_path), timeout=0.3)
    lines: list[str] = []
    code = installer.run([str(brew), "install", "jq"], lines.append)
    assert code != 0
    assert lines[0] == "start" and lines[-1].startswith("coffer: stopped after")

"""The machine adapter of the required-command check, against scripts this
test writes."""

from __future__ import annotations

import pathlib

from coffer.infrastructure.platform.user_path import UserPath
from coffer.infrastructure.skill.command_probe import CommandProbe


def _script(bin_dir: pathlib.Path, name: str, body: str) -> pathlib.Path:
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _path(bin_dir: pathlib.Path) -> UserPath:
    shell = str(bin_dir)
    return UserPath(shell_path=lambda: shell)


def test_probe_reads_the_version(tmp_path: pathlib.Path) -> None:
    gh = _script(tmp_path, "gh", 'case "$1" in --version) echo "gh version 2.45.0";; esac')
    probe = CommandProbe(user_path=_path(tmp_path))
    assert probe.locate("gh") == str(gh.resolve())
    assert probe.locate("no-such-command-xyz") is None
    assert probe.version(str(gh)) == "2.45.0"


def test_a_tool_that_prints_no_version_reads_as_none(tmp_path: pathlib.Path) -> None:
    # ``go --version`` prints an error and no version.
    go = _script(tmp_path, "go", 'echo "flag provided but not defined: -version" >&2; exit 2')
    assert CommandProbe(user_path=_path(tmp_path)).version(str(go)) is None

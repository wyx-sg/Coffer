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


def test_probe_finds_the_command_and_runs_nothing(tmp_path: pathlib.Path) -> None:
    ran = tmp_path / "ran"
    gh = _script(tmp_path, "gh", f'touch "{ran}"')
    probe = CommandProbe(user_path=_path(tmp_path))
    assert probe.locate("gh") == str(gh.resolve())
    assert probe.locate("no-such-command-xyz") is None
    assert not ran.exists()

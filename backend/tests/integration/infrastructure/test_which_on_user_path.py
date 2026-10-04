"""A program the person runs from a terminal is found although the daemon's
own ``PATH`` (a GUI launch's) does not list its directory — the lookup the
chat providers decide availability and start the agent with."""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.platform import user_path
from coffer.infrastructure.platform.process import login_shell_path


def test_a_program_only_on_the_login_shell_path_is_found(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shell_dir = tmp_path / "shell-bin"
    shell_dir.mkdir()
    program = shell_dir / "codex"
    program.write_text("#!/bin/sh\n", encoding="utf-8")
    program.chmod(0o755)
    daemon_dir = tmp_path / "daemon-bin"
    daemon_dir.mkdir()
    monkeypatch.setenv("PATH", str(daemon_dir))
    monkeypatch.setitem(user_path._SHELL_PATHS, login_shell_path, str(shell_dir))

    assert user_path.which_on_user_path("codex") == str(program)
    assert user_path.which_on_user_path("claude") is None

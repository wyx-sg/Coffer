"""The user's PATH is asked of an interactive login shell, so the lines nvm and
most installers add to ``~/.zshrc`` count; a profile that fails interactively
still gets the login-only answer, and chatter around the value is ignored."""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.platform import process
from coffer.infrastructure.platform.host import HostOs

# A stand-in shell: with -ilc it prints the rc file's PATH (and a greeting, as a
# profile might); without it, the login-only PATH. INTERACTIVE_FAILS makes the
# interactive run exit before printing anything.
_SHELL = """#!/bin/sh
case "$1" in
  -ilc)
    [ -n "$INTERACTIVE_FAILS" ] && exit 1
    echo "Welcome back"
    PATH="/Users/me/.nvm/versions/node/v24/bin:/usr/bin"
    ;;
  *) PATH="/usr/bin" ;;
esac
shift
eval "$1"
echo "done"
"""


@pytest.fixture
def fake_shell(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shell = tmp_path / "fakesh"
    shell.write_text(_SHELL, encoding="utf-8")
    shell.chmod(0o755)
    monkeypatch.setenv("SHELL", str(shell))
    monkeypatch.setattr(process, "host_os", lambda: HostOs.MACOS)


@pytest.mark.acceptance(
    spec="agent-registry", scenario="find a program a Node version manager installed"
)
@pytest.mark.usefixtures("fake_shell")
def test_the_path_comes_from_an_interactive_login_shell() -> None:
    assert process.login_shell_path() == "/Users/me/.nvm/versions/node/v24/bin:/usr/bin"


@pytest.mark.acceptance(
    spec="agent-registry", scenario="find a program a Node version manager installed"
)
@pytest.mark.usefixtures("fake_shell")
def test_a_profile_that_fails_interactively_gets_the_login_only_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INTERACTIVE_FAILS", "1")
    assert process.login_shell_path() == "/usr/bin"

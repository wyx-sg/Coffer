"""An agent Coffer starts for a turn gets the PATH the CLIs page checks
commands on (spec skill-manager "Check every required command where the
agent runs")."""

from __future__ import annotations

import pytest

from coffer.infrastructure.platform import user_path


def _login_shell(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    real = user_path.UserPath
    monkeypatch.setattr(user_path, "UserPath", lambda: real(shell_path=lambda: path))


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="an agent Coffer starts gets the path its commands are checked on",
)
def test_the_users_path_is_set_when_the_daemons_differs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    _login_shell(monkeypatch, "/opt/homebrew/bin:/usr/bin")
    assert user_path.user_path_env() == {"PATH": "/opt/homebrew/bin:/usr/bin:/bin"}


def test_nothing_is_set_when_the_daemon_already_has_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/opt/homebrew/bin:/usr/bin")
    _login_shell(monkeypatch, "/opt/homebrew/bin:/usr/bin")
    assert user_path.user_path_env() == {}

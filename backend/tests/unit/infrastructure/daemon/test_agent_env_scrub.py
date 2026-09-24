"""The daemon drops an inherited ``CLAUDE_CONFIG_DIR`` / ``CODEX_HOME`` at start.

A daemon started from a shell that exports either variable would otherwise
hand it to every agent it spawns, so a default-directory agent would run
against the exported directory while Coffer delivers into ``~/.claude`` /
``~/.codex``. Agents get the variables only through their registered config
directory (spec daemon "Clear inherited agent-home variables at start").
"""

from __future__ import annotations

import logging
import os
import pathlib

import pytest

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.infrastructure.agent.codex_rpc_models import CodexRpcModelDiscovery
from coffer.infrastructure.daemon import entry


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a daemon started from a shell exporting an agent home does not pass it on",
)
def test_scrub_removes_both_variables_and_logs_once(caplog: pytest.LogCaptureFixture) -> None:
    environ = {
        "PATH": "/usr/bin",
        "CLAUDE_CONFIG_DIR": "/elsewhere/claude",
        "CODEX_HOME": "/elsewhere/codex",
    }
    with caplog.at_level(logging.INFO, logger=entry.__name__):
        removed = entry.scrub_agent_home_env(environ)

    assert sorted(removed) == ["CLAUDE_CONFIG_DIR", "CODEX_HOME"]
    assert environ == {"PATH": "/usr/bin"}
    lines = [r.getMessage() for r in caplog.records if "CLAUDE_CONFIG_DIR" in r.getMessage()]
    assert len(lines) == 1
    assert "CODEX_HOME" in lines[0]


def test_scrub_is_silent_when_nothing_was_inherited(caplog: pytest.LogCaptureFixture) -> None:
    environ = {"PATH": "/usr/bin"}
    with caplog.at_level(logging.INFO, logger=entry.__name__):
        removed = entry.scrub_agent_home_env(environ)

    assert removed == []
    assert environ == {"PATH": "/usr/bin"}
    assert not [r for r in caplog.records if r.name == entry.__name__]


def test_main_scrubs_before_anything_else(monkeypatch: pytest.MonkeyPatch) -> None:
    """``main`` clears the daemon's own environment before it binds or serves,
    so nothing it later spawns can inherit the variables."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/elsewhere/claude")
    monkeypatch.setenv("CODEX_HOME", "/elsewhere/codex")
    seen: dict[str, str | None] = {}

    def _stop_at_acquire() -> None:
        seen["claude"] = os.environ.get("CLAUDE_CONFIG_DIR")
        seen["codex"] = os.environ.get("CODEX_HOME")
        raise SystemExit(0)

    monkeypatch.setattr(entry, "_raise_fd_soft_limit", lambda: None)
    monkeypatch.setattr(entry, "_install_signal_handlers", lambda: None)
    monkeypatch.setattr(entry.bootstrap, "acquire_or_existing", _stop_at_acquire)

    with pytest.raises(SystemExit):
        entry.main()

    assert seen == {"claude": None, "codex": None}


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a daemon started from a shell exporting an agent home does not pass it on",
)
def test_default_dir_agent_turn_env_carries_neither_variable(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the scrub, the env a default-directory agent's turn is spawned
    with — the daemon's own, merged with the agent's overrides (none) — holds
    neither variable; a custom-directory agent still gets its own one."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "exported-claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "exported-codex"))

    entry.scrub_agent_home_env(os.environ)

    for agent_type in (AgentType.CLAUDE_CODE, AgentType.CODEX):
        overrides = AgentConfig(type=agent_type).runtime_env()
        assert overrides == {}
        turn_env = {**os.environ, **overrides}
        assert "CLAUDE_CONFIG_DIR" not in turn_env
        assert "CODEX_HOME" not in turn_env

    # The Codex model probe for the default home inherits the (scrubbed) env.
    assert CodexRpcModelDiscovery._env(tmp_path / ".codex") is None

    custom = tmp_path / "work-codex"
    custom_env = {
        **os.environ,
        **AgentConfig(type=AgentType.CODEX, config_dir=str(custom)).runtime_env(),
    }
    assert custom_env["CODEX_HOME"] == str(custom)
    assert "CLAUDE_CONFIG_DIR" not in custom_env

"""Each agent's own command line reads the MCP entry Coffer writes for it.

ADR cursor-opencode-and-deepseek-harness-are-supported-agents: the agents
Coffer supports must be exercised on a real install, and for the agents not on
the maintainer's machine a CI job provides that. The job (``agent-cli`` in
``.github/workflows/verify.yml``) installs each agent's command line and runs
this module with ``COFFER_AGENT_CLI_SMOKE=1``. Each test writes Coffer's entry
with the same domain transform the daemon uses, pointing at a one-tool stdio
server, and asks the agent what it sees. A missing program skips its test.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

import pytest

from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.mcp_install import apply_install
from coffer.domain.agent.types import AgentType

pytestmark = pytest.mark.skipif(
    os.environ.get("COFFER_AGENT_CLI_SMOKE") != "1",
    reason="runs in the agent-cli CI job, which installs the agents",
)

SERVER = pathlib.Path(__file__).with_name("fake_mcp_server.py")


def _shim(tmp_path: pathlib.Path) -> str:
    shim = tmp_path / "coffer-mcp-shim"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{SERVER}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    return str(shim)


def _install(agent_type: AgentType, home: pathlib.Path, shim: str) -> pathlib.Path:
    d = descriptor_for(agent_type)
    assert d.mcp is not None
    cfg = home / d.config_subpath
    spec = next(s for s in d.config_files(cfg) if s.key == d.mcp.config_key)
    spec.path.parent.mkdir(parents=True, exist_ok=True)
    text = spec.path.read_text(encoding="utf-8") if spec.path.exists() else ""
    spec.path.write_text(
        apply_install(
            d.mcp.format,
            text,
            shim,
            container_key=d.mcp.container_key,
            entry_style=d.mcp.entry_style,
            agent_uid="smoke-uid",
            extras=d.mcp.entry_extras,
        ),
        encoding="utf-8",
    )
    return spec.path


def _env(home: pathlib.Path, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
    env.update(HOME=str(home), NO_COLOR="1", **extra)
    return env


def _run(argv: list[str], env: dict[str, str], timeout: float = 180) -> str:
    done = subprocess.run(  # noqa: S603 - fixed argv
        argv, env=env, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL
    )
    return done.stdout + done.stderr


def _program(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        pytest.skip(f"{name} is not installed")
    return found


def test_opencode_lists_coffer(tmp_path: pathlib.Path, monkeypatch) -> None:
    opencode = _program("opencode")
    monkeypatch.setenv("HOME", str(tmp_path))
    _install(AgentType.OPENCODE, tmp_path, _shim(tmp_path))
    out = _run([opencode, "mcp", "list"], _env(tmp_path))
    assert "coffer" in out, out


def test_deepseek_harness_composes_the_coffer_row(tmp_path: pathlib.Path, monkeypatch) -> None:
    dsh = _program("dsh")
    monkeypatch.setenv("HOME", str(tmp_path))
    _install(AgentType.DEEPSEEK_HARNESS, tmp_path, _shim(tmp_path))
    out = _run(
        [dsh, "--profile", "web", "--dump-config"],
        _env(tmp_path, DSH_HOME=str(tmp_path / ".dsh")),
    )
    assert "coffer-mcp" in out, out


def test_cursor_lists_coffer(tmp_path: pathlib.Path, monkeypatch) -> None:
    agent = _program("cursor-agent")
    monkeypatch.setenv("HOME", str(tmp_path))
    _install(AgentType.CURSOR, tmp_path, _shim(tmp_path))
    out = _run([agent, "mcp", "list"], _env(tmp_path))
    if "login" in out.lower() and "coffer" not in out:
        pytest.skip(f"cursor-agent wants a sign-in to list servers: {out[:200]}")
    assert "coffer" in out, out

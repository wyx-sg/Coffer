"""Each agent's own command line reads the MCP entry Coffer writes for it.

ADR cursor-opencode-and-deepseek-harness-are-supported-agents: the agents
Coffer supports must be exercised on a real install, and for the agents not on
the maintainer's machine a CI job provides that. The job (``agent-cli`` in
``.github/workflows/verify.yml``) installs each agent's command line and runs
this module with ``COFFER_SMOKE_AGENT_CLI=1``. Each test writes Coffer's entry
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
    os.environ.get("COFFER_SMOKE_AGENT_CLI") != "1",
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
    done = subprocess.run(
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
    if "--standalone" in _run([opencode, "--help"], _env(tmp_path)):
        # OpenCode 2.x: ``mcp list`` reports no server at all, its own entries
        # included, so read the config it resolved instead. It files the 1.x
        # entry Coffer writes under its own ``mcp.servers`` map.
        out = _run([opencode, "debug", "config", "--standalone"], _env(tmp_path))
        assert '"servers"' in out and '"coffer"' in out, out
        assert "coffer-mcp-shim" in out, out
    else:
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


def test_opencode_calls_the_proxy_with_the_token_from_its_file(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """ADR opencode-reads-its-proxy-token-from-a-file: the provider block Coffer
    writes makes OpenCode send the Responses API to the proxy's address, with
    the token read from the file the ``{file:…}`` key names."""
    import http.server
    import json
    import threading

    from coffer.domain.provider.agent_projection import (
        OpenCodeProviderProjection,
        ProviderProjectionRequest,
    )
    from coffer.domain.provider.codex_projection import CodexAuthCommand
    from coffer.domain.provider.model_binding import ModelBinding, ProjectedModel

    opencode = _program("opencode")
    monkeypatch.setenv("HOME", str(tmp_path))
    seen: list[tuple[str, str | None]] = []
    got = threading.Event()

    class Upstream(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("content-length") or 0))
            seen.append((self.path, self.headers.get("authorization")))
            got.set()
            body = json.dumps({"error": {"message": "smoke test stop"}}).encode()
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    token_file = tmp_path / ".coffer" / "local" / "proxy-tokens" / "opencode"
    token_file.parent.mkdir(parents=True)
    token_file.write_text("cfr_smoke", encoding="utf-8")
    config = tmp_path / descriptor_for(AgentType.OPENCODE).config_subpath / "opencode.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    request = ProviderProjectionRequest(
        connection_uid="0" * 32,
        connection_name="smoke",
        agent_uid="smoke-uid",
        base_url=f"http://127.0.0.1:{server.server_address[1]}/openai/v1",
        key_helper="",
        codex_auth=CodexAuthCommand("", ()),
        binding=ModelBinding(model="smoke-model"),
        models=(ProjectedModel("smoke-model", 128_000),),
        token_file=token_file,
    )
    config.write_text(
        OpenCodeProviderProjection().apply("", request, config).text, encoding="utf-8"
    )
    standalone = "--standalone" in _run([opencode, "--help"], _env(tmp_path))
    argv = [opencode, "run", *(["--standalone"] if standalone else []), "hi"]
    proc = subprocess.Popen(
        argv,
        env=_env(tmp_path),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        assert got.wait(180), "OpenCode never called the provider"
    finally:
        proc.kill()
        proc.wait()
        server.shutdown()
    assert ("/openai/v1/responses", "Bearer cfr_smoke") in seen, seen

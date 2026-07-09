"""Integration tests for AgentMcpService (install/uninstall/status).

Covers spec 004 acceptance scenarios for one-click Coffer-MCP install.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from coffer.application.agent.mcp_service import AgentMcpService
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ShimNotFound
from coffer.infrastructure.agent.config_file_store import ConfigFileStore

pytestmark = pytest.mark.asyncio

SHIM = "/opt/coffer/coffer-mcp-shim"


async def _register_claude(bundle, home: pathlib.Path):
    (home / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    await bundle.svc.register(agent_type=AgentType.CLAUDE_CODE, name="cc", actor="cli")


async def _register_codex(bundle, home: pathlib.Path):
    (home / ".codex" / "skills").mkdir(parents=True, exist_ok=True)
    await bundle.svc.register(agent_type=AgentType.CODEX, name="cx", actor="cli")


@pytest.mark.acceptance(spec="004-agent-registry", scenario="report Coffer-MCP install status")
async def test_status_false_when_absent(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    st = await agent_bundle.mcp.status("cc")
    assert st.installed is False
    assert st.command is None


@pytest.mark.acceptance(spec="004-agent-registry", scenario="install Coffer's MCP into an agent")
async def test_install_claude_writes_entry_with_backup_and_audit(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(json.dumps({"oauthAccount": {"id": "x"}}), encoding="utf-8")

    st = await agent_bundle.mcp.install("cc", actor="ui")
    assert st.installed is True
    assert st.command == SHIM
    data = json.loads(claude_json.read_text())
    assert data["mcpServers"]["coffer"] == {"command": SHIM}
    # Untouched neighbouring state preserved; prior file backed up.
    assert data["oauthAccount"] == {"id": "x"}
    assert (tmp_path / ".claude.json.bak").exists()

    rows = await agent_bundle.audit.query(
        kind="agent", name="cc", event_type=AuditEventType.AGENT_MCP_INSTALLED.value
    )
    assert len(rows) == 1
    assert rows[0].details.get("command") == SHIM


@pytest.mark.acceptance(spec="004-agent-registry", scenario="install Coffer's MCP into an agent")
async def test_install_codex_writes_toml(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_codex(agent_bundle, tmp_path)
    cfg = tmp_path / ".codex" / "config.toml"
    cfg.write_text('model = "o1"\n', encoding="utf-8")

    st = await agent_bundle.mcp.install("cx", actor="ui")
    assert st.installed is True
    text = cfg.read_text()
    assert 'model = "o1"' in text  # preserved
    assert "[mcp_servers.coffer]" in text
    assert await _status(agent_bundle, "cx") is True


@pytest.mark.acceptance(spec="004-agent-registry", scenario="install Coffer's MCP is idempotent")
async def test_install_idempotent(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    await agent_bundle.mcp.install("cc", actor="ui")
    await agent_bundle.mcp.install("cc", actor="ui")
    data = json.loads((tmp_path / ".claude.json").read_text())
    assert list(data["mcpServers"]).count("coffer") == 1
    assert (await agent_bundle.mcp.status("cc")).installed is True


@pytest.mark.acceptance(spec="004-agent-registry", scenario="uninstall Coffer's MCP from an agent")
async def test_uninstall_removes_entry(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    await agent_bundle.mcp.install("cc", actor="ui")

    st = await agent_bundle.mcp.uninstall("cc", actor="ui")
    assert st.installed is False
    data = json.loads((tmp_path / ".claude.json").read_text())
    assert "coffer" not in data.get("mcpServers", {})
    rows = await agent_bundle.audit.query(
        kind="agent", name="cc", event_type=AuditEventType.AGENT_MCP_UNINSTALLED.value
    )
    assert len(rows) == 1


async def test_uninstall_when_absent_is_noop(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    st = await agent_bundle.mcp.uninstall("cc", actor="ui")
    assert st.installed is False
    # No file created, no audit row.
    assert not (tmp_path / ".claude.json").exists()
    rows = await agent_bundle.audit.query(
        kind="agent", name="cc", event_type=AuditEventType.AGENT_MCP_UNINSTALLED.value
    )
    assert rows == []


async def test_install_raises_when_shim_unresolvable(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)

    def _boom() -> str:
        raise ShimNotFound()

    svc = AgentMcpService(
        agent_service=agent_bundle.svc,
        audit=agent_bundle.audit,
        store=ConfigFileStore(),
        shim_resolver=_boom,
    )
    with pytest.raises(ShimNotFound):
        await svc.install("cc", actor="ui")
    # Nothing written.
    assert not (tmp_path / ".claude.json").exists()


async def _status(bundle, name):
    st = await bundle.mcp.status(name)
    return st.installed


# --- openclaw nested container (ADR-043) -----------------------------------------


async def _register_openclaw(bundle, home: pathlib.Path):
    (home / ".openclaw" / "skills").mkdir(parents=True, exist_ok=True)
    await bundle.svc.register(agent_type=AgentType.OPENCLAW, name="ow", actor="cli")


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="install Coffer's MCP into OpenClaw's nested servers map"
)
async def test_install_openclaw_writes_nested_mcp_servers(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_openclaw(agent_bundle, tmp_path)
    config = tmp_path / ".openclaw" / "openclaw.json"
    config.write_text(
        json.dumps({"gateway": {"port": 18789}, "mcp": {"servers": {"files": {"command": "npx"}}}}),
        encoding="utf-8",
    )

    st = await agent_bundle.mcp.install("ow", actor="ui")
    assert st.installed is True
    assert st.command == SHIM

    data = json.loads(config.read_text())
    # The entry lands INSIDE the nested `mcp.servers` map, command-map shape.
    assert data["mcp"]["servers"]["coffer"] == {"command": SHIM}
    assert data["mcp"]["servers"]["files"] == {"command": "npx"}  # user server kept
    assert data["gateway"] == {"port": 18789}  # unrelated key preserved
    assert (tmp_path / ".openclaw" / "openclaw.json.bak").exists()

    # Status reads through the nested path; uninstall removes only Coffer's.
    assert (await agent_bundle.mcp.status("ow")).installed is True
    await agent_bundle.mcp.uninstall("ow", actor="ui")
    data = json.loads(config.read_text())
    assert "coffer" not in data["mcp"]["servers"]
    assert data["mcp"]["servers"]["files"] == {"command": "npx"}
    assert (await agent_bundle.mcp.status("ow")).installed is False

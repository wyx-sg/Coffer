"""Integration tests for AgentMcpService (install/uninstall/status).

Covers spec agent-registry acceptance scenarios for one-click Coffer-MCP install.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from coffer.application.agent.mcp_service import AgentMcpService
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ShimNotFound
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore

pytestmark = pytest.mark.asyncio

SHIM = "/opt/coffer/coffer-mcp-shim"


async def _register_claude(bundle, home: pathlib.Path) -> Resource:
    """Register the Claude agent and hand back the ROW — every call below
    addresses it by ``uid``, and the audit queries filter on the resource
    itself rather than on the label it happens to carry."""
    (home / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    return await bundle.svc.register(agent_type=AgentType.CLAUDE_CODE, name="cc", actor="cli")


async def _register_codex(bundle, home: pathlib.Path) -> Resource:
    (home / ".codex" / "skills").mkdir(parents=True, exist_ok=True)
    return await bundle.svc.register(agent_type=AgentType.CODEX, name="cx", actor="cli")


@pytest.mark.acceptance(spec="agent-registry", scenario="report Coffer-MCP install status")
async def test_status_false_when_absent(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent = await _register_claude(agent_bundle, tmp_path)
    st = await agent_bundle.mcp.status(agent.uid)
    assert st.installed is False
    assert st.command is None


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="install Coffer's MCP into an agent",
)
async def test_install_claude_writes_entry_with_backup_and_audit(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent = await _register_claude(agent_bundle, tmp_path)
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(json.dumps({"oauthAccount": {"id": "x"}}), encoding="utf-8")

    st = await agent_bundle.mcp.install(agent.uid, actor="ui")
    assert st.installed is True
    assert st.command == SHIM
    data = json.loads(claude_json.read_text())
    # spec agent-registry FR-015 (amended): install threads the agent's own UID
    # through as `--agent-uid <uid>` so the shim self-reports an identity the
    # gateway can still match after the agent is renamed.
    assert data["mcpServers"]["coffer"] == {
        "command": SHIM,
        "args": ["--agent-uid", agent.uid],
    }
    # Untouched neighbouring state preserved; prior file backed up.
    assert data["oauthAccount"] == {"id": "x"}
    assert (tmp_path / ".claude.json.bak").exists()

    rows = await agent_bundle.audit.query(
        resource=agent, event_type=AuditEventType.AGENT_MCP_INSTALLED.value
    )
    assert len(rows) == 1
    assert rows[0].details.get("command") == SHIM


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="install Coffer's MCP into an agent",
)
async def test_install_codex_writes_toml(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent = await _register_codex(agent_bundle, tmp_path)
    cfg = tmp_path / ".codex" / "config.toml"
    cfg.write_text('model = "o1"\n', encoding="utf-8")

    st = await agent_bundle.mcp.install(agent.uid, actor="ui")
    assert st.installed is True
    text = cfg.read_text()
    assert 'model = "o1"' in text  # preserved
    assert "[mcp_servers.coffer]" in text
    assert await _status(agent_bundle, agent.uid) is True


@pytest.mark.acceptance(spec="agent-registry", scenario="install Coffer's MCP is idempotent")
async def test_install_idempotent(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent = await _register_claude(agent_bundle, tmp_path)
    await agent_bundle.mcp.install(agent.uid, actor="ui")
    await agent_bundle.mcp.install(agent.uid, actor="ui")
    data = json.loads((tmp_path / ".claude.json").read_text())
    assert list(data["mcpServers"]).count("coffer") == 1
    assert data["mcpServers"]["coffer"]["args"] == ["--agent-uid", agent.uid]
    assert (await agent_bundle.mcp.status(agent.uid)).installed is True


async def test_reinstall_upgrades_preexisting_entry_without_args(
    agent_bundle, tmp_path, monkeypatch
):
    """An older Coffer wrote a coffer entry with no identity flag at all.
    `status` must still report them installed, and re-install (the upgrade path
    — there is no auto-migration) rewrites the entry with the flag, in place."""
    monkeypatch.setenv("HOME", str(tmp_path))
    agent = await _register_claude(agent_bundle, tmp_path)
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(
        json.dumps({"mcpServers": {"coffer": {"command": SHIM}}}), encoding="utf-8"
    )

    pre = await agent_bundle.mcp.status(agent.uid)
    assert pre.installed is True
    assert pre.command == SHIM

    st = await agent_bundle.mcp.install(agent.uid, actor="ui")
    assert st.installed is True
    data = json.loads(claude_json.read_text())
    assert list(data["mcpServers"]).count("coffer") == 1
    assert data["mcpServers"]["coffer"] == {
        "command": SHIM,
        "args": ["--agent-uid", agent.uid],
    }


@pytest.mark.acceptance(spec="agent-registry", scenario="uninstall Coffer's MCP from an agent")
async def test_uninstall_removes_entry(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent = await _register_claude(agent_bundle, tmp_path)
    await agent_bundle.mcp.install(agent.uid, actor="ui")

    st = await agent_bundle.mcp.uninstall(agent.uid, actor="ui")
    assert st.installed is False
    data = json.loads((tmp_path / ".claude.json").read_text())
    assert "coffer" not in data.get("mcpServers", {})
    rows = await agent_bundle.audit.query(
        resource=agent, event_type=AuditEventType.AGENT_MCP_UNINSTALLED.value
    )
    assert len(rows) == 1


async def test_uninstall_when_absent_is_noop(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent = await _register_claude(agent_bundle, tmp_path)
    st = await agent_bundle.mcp.uninstall(agent.uid, actor="ui")
    assert st.installed is False
    # No file created, no audit row.
    assert not (tmp_path / ".claude.json").exists()
    rows = await agent_bundle.audit.query(
        resource=agent, event_type=AuditEventType.AGENT_MCP_UNINSTALLED.value
    )
    assert rows == []


async def test_install_raises_when_shim_unresolvable(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent = await _register_claude(agent_bundle, tmp_path)

    def _boom() -> str:
        raise ShimNotFound()

    svc = AgentMcpService(
        agent_service=agent_bundle.svc,
        audit=agent_bundle.audit,
        store=ConfigFileStore(),
        shim_resolver=_boom,
    )
    with pytest.raises(ShimNotFound):
        await svc.install(agent.uid, actor="ui")
    # Nothing written.
    assert not (tmp_path / ".claude.json").exists()


async def _status(bundle, uid):
    st = await bundle.mcp.status(uid)
    return st.installed

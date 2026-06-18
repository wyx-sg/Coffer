"""End-to-end registration + Coffer-MCP install for the agents added on top of
Claude Code / Codex: Cursor, OpenCode, OpenClaw, Hermes.

Proves the capability manifest drives detect/register/config-files/MCP for each
new agent, including the per-agent MCP shape (container key + entry style +
file format).
"""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml

from coffer.domain.agent.types import AgentType

pytestmark = pytest.mark.asyncio

SHIM = "/opt/coffer/coffer-mcp-shim"


async def _register(bundle, home: pathlib.Path, agent_type: AgentType, name: str) -> None:
    cfg_dir = home / agent_type.config_dir().relative_to(home)
    (cfg_dir / "skills").mkdir(parents=True, exist_ok=True)
    await bundle.svc.register(agent_type=agent_type, name=name, actor="cli")


# (agent_type, name, mcp file relative to config_dir) ---------------------------
_AGENTS = [
    (AgentType.CURSOR, "cur", "mcp.json"),
    (AgentType.OPENCODE, "oc", "opencode.json"),
    (AgentType.OPENCLAW, "claw", "openclaw.json"),
    (AgentType.HERMES, "herm", "config.yaml"),
]


@pytest.mark.parametrize("agent_type,name,_mcp_file", _AGENTS)
async def test_new_agent_register_and_status(
    agent_bundle, tmp_path, monkeypatch, agent_type, name, _mcp_file
):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register(agent_bundle, tmp_path, agent_type, name)
    st = await agent_bundle.mcp.status(name)
    assert st.installed is False and st.command is None


@pytest.mark.parametrize("agent_type,name,mcp_file", _AGENTS)
async def test_new_agent_install_uninstall_roundtrip(
    agent_bundle, tmp_path, monkeypatch, agent_type, name, mcp_file
):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register(agent_bundle, tmp_path, agent_type, name)

    st = await agent_bundle.mcp.install(name, actor="ui")
    assert st.installed is True and st.command == SHIM
    assert (await agent_bundle.mcp.status(name)).installed is True

    # idempotent — second install does not duplicate
    await agent_bundle.mcp.install(name, actor="ui")
    assert (await agent_bundle.mcp.status(name)).installed is True

    # uninstall removes it
    st = await agent_bundle.mcp.uninstall(name, actor="ui")
    assert st.installed is False
    assert (await agent_bundle.mcp.status(name)).installed is False


async def test_cursor_writes_mcpservers_command_map(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register(agent_bundle, tmp_path, AgentType.CURSOR, "cur")
    await agent_bundle.mcp.install("cur", actor="ui")
    data = json.loads((tmp_path / ".cursor" / "mcp.json").read_text())
    # ADR-026: install embeds the agent identity as an `--agent <name>` arg.
    assert data["mcpServers"]["coffer"] == {"command": SHIM, "args": ["--agent", "cur"]}


async def test_opencode_writes_mcp_typed_command_array(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register(agent_bundle, tmp_path, AgentType.OPENCODE, "oc")
    await agent_bundle.mcp.install("oc", actor="ui")
    data = json.loads((tmp_path / ".config" / "opencode" / "opencode.json").read_text())
    # OpenCode: container `mcp`, typed command-array entry; ADR-026 appends
    # the `--agent <name>` arg to the command array.
    assert data["mcp"]["coffer"] == {"type": "local", "command": [SHIM, "--agent", "oc"]}


async def test_openclaw_writes_mcp_command_map(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register(agent_bundle, tmp_path, AgentType.OPENCLAW, "claw")
    await agent_bundle.mcp.install("claw", actor="ui")
    data = json.loads((tmp_path / ".openclaw" / "openclaw.json").read_text())
    assert data["mcp"]["coffer"] == {"command": SHIM, "args": ["--agent", "claw"]}


async def test_hermes_writes_yaml_mcp_servers_preserving_comments(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register(agent_bundle, tmp_path, AgentType.HERMES, "herm")
    cfg = tmp_path / ".hermes" / "config.yaml"
    cfg.write_text("# my hermes\nmodel: gpt\n", encoding="utf-8")
    await agent_bundle.mcp.install("herm", actor="ui")
    text = cfg.read_text()
    assert "# my hermes" in text  # round-trip preserved the user's comment
    data = yaml.safe_load(text)
    assert data["model"] == "gpt"
    assert data["mcp_servers"]["coffer"]["command"] == SHIM

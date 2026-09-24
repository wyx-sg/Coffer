"""Boot migration: a Claude Code agent's MCP entry moves out of ``~/.claude.json``.

Before Coffer honoured a custom config directory for ``.claude.json``, it
installed every Claude Code agent's entry into ``$HOME/.claude.json`` (with
that agent's uid in the shim args). Claude Code under ``CLAUDE_CONFIG_DIR``
never reads that file, so the custom agent showed "not installed" while the
default agent showed "installed" under the wrong identity. The boot migration
moves such an entry into ``<config_dir>/.claude.json`` once (spec
agent-registry/claude-code
"Install Coffer's MCP entry into Claude Code's .claude.json").
"""

from __future__ import annotations

import json
import logging
import pathlib

import pytest

from coffer.application.agent.mcp_home_migration import ClaudeHomeMcpEntryMigration
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore

pytestmark = pytest.mark.asyncio

SHIM = "/opt/coffer/coffer-mcp-shim"


async def _agents(bundle, home: pathlib.Path) -> tuple[Resource, Resource, pathlib.Path]:
    (home / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    default = await bundle.svc.register(agent_type=AgentType.CLAUDE_CODE, name="cc", actor="cli")
    custom_dir = home / "work-claude"
    custom_dir.mkdir()
    custom = await bundle.svc.register(
        agent_type=AgentType.CLAUDE_CODE,
        name="work",
        config_dir=str(custom_dir),
        actor="cli",
    )
    return default, custom, custom_dir


def _entry(uid: str) -> dict[str, object]:
    return {"command": SHIM, "args": ["--agent-uid", uid]}


def _migration(bundle) -> ClaudeHomeMcpEntryMigration:
    return ClaudeHomeMcpEntryMigration(
        agent_service=bundle.svc, audit=bundle.audit, store=ConfigFileStore()
    )


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="an entry installed before the config dir was honoured moves to the agent's own file",
)
async def test_stale_home_entry_of_custom_agent_moves_to_its_own_file(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    _default, custom, custom_dir = await _agents(agent_bundle, tmp_path)
    home_json = tmp_path / ".claude.json"
    home_json.write_text(
        json.dumps(
            {
                "oauthAccount": {"id": "x"},
                "mcpServers": {"coffer": _entry(custom.uid), "other": {"command": "o"}},
            }
        ),
        encoding="utf-8",
    )
    inner_json = custom_dir / ".claude.json"
    inner_json.write_text(json.dumps({"projects": {"/p": {}}}), encoding="utf-8")

    assert (await agent_bundle.mcp.status(custom.uid)).installed is False

    notes = await _migration(agent_bundle).heal()

    home = json.loads(home_json.read_text())
    inner = json.loads(inner_json.read_text())
    assert home == {"oauthAccount": {"id": "x"}, "mcpServers": {"other": {"command": "o"}}}
    assert inner == {"projects": {"/p": {}}, "mcpServers": {"coffer": _entry(custom.uid)}}
    # Both writes keep what was there, as install/uninstall do.
    assert (tmp_path / ".claude.json.bak").exists()
    assert (custom_dir / ".claude.json.bak").exists()
    assert (await agent_bundle.mcp.status(custom.uid)).installed is True
    installed = await agent_bundle.audit.query(
        resource=custom, event_type=AuditEventType.AGENT_MCP_INSTALLED.value
    )
    uninstalled = await agent_bundle.audit.query(
        resource=custom, event_type=AuditEventType.AGENT_MCP_UNINSTALLED.value
    )
    assert [r.details.get("path") for r in installed] == [str(inner_json)]
    assert [r.details.get("path") for r in uninstalled] == [str(home_json)]
    assert installed[0].actor == "system"
    assert len(notes) == 1 and custom.uid in notes[0]


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="an entry installed before the config dir was honoured moves to the agent's own file",
)
async def test_second_run_is_a_no_op(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _default, custom, custom_dir = await _agents(agent_bundle, tmp_path)
    home_json = tmp_path / ".claude.json"
    home_json.write_text(json.dumps({"mcpServers": {"coffer": _entry(custom.uid)}}))

    await _migration(agent_bundle).heal()
    home_after = home_json.read_bytes()
    inner_after = (custom_dir / ".claude.json").read_bytes()

    assert await _migration(agent_bundle).heal() == []
    assert home_json.read_bytes() == home_after
    assert (custom_dir / ".claude.json").read_bytes() == inner_after
    rows = await agent_bundle.audit.query(
        resource=custom, event_type=AuditEventType.AGENT_MCP_INSTALLED.value
    )
    assert len(rows) == 1


async def test_entry_already_in_agent_file_is_kept_and_home_one_removed(
    agent_bundle, tmp_path, monkeypatch
):
    """The agent's own file already has an entry (a re-install since): it is
    left exactly as is; only the stale home copy goes."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _default, custom, custom_dir = await _agents(agent_bundle, tmp_path)
    home_json = tmp_path / ".claude.json"
    home_json.write_text(json.dumps({"mcpServers": {"coffer": _entry(custom.uid)}}))
    inner_json = custom_dir / ".claude.json"
    inner_entry = {"command": "/newer/shim", "args": ["--agent-uid", custom.uid]}
    inner_json.write_text(json.dumps({"mcpServers": {"coffer": inner_entry}}))
    inner_before = inner_json.read_bytes()

    await _migration(agent_bundle).heal()

    assert inner_json.read_bytes() == inner_before
    assert json.loads(home_json.read_text()) == {"mcpServers": {}}


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="an entry installed before the config dir was honoured moves to the agent's own file",
)
async def test_entry_of_the_default_agent_is_untouched(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    default, _custom, custom_dir = await _agents(agent_bundle, tmp_path)
    home_json = tmp_path / ".claude.json"
    home_json.write_text(json.dumps({"mcpServers": {"coffer": _entry(default.uid)}}))
    before = home_json.read_bytes()

    assert await _migration(agent_bundle).heal() == []

    assert home_json.read_bytes() == before
    assert not (custom_dir / ".claude.json").exists()


async def test_entry_without_uid_or_foreign_uid_is_untouched(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _default, _custom, custom_dir = await _agents(agent_bundle, tmp_path)
    home_json = tmp_path / ".claude.json"
    for entry in ({"command": SHIM}, _entry("some-other-uid"), {"command": "not-coffer"}):
        home_json.write_text(json.dumps({"mcpServers": {"coffer": entry}}))
        before = home_json.read_bytes()
        assert await _migration(agent_bundle).heal() == []
        assert home_json.read_bytes() == before
    assert not (custom_dir / ".claude.json").exists()


async def test_unparseable_files_are_left_alone_and_logged(
    agent_bundle, tmp_path, monkeypatch, caplog
):
    monkeypatch.setenv("HOME", str(tmp_path))
    _default, custom, custom_dir = await _agents(agent_bundle, tmp_path)
    home_json = tmp_path / ".claude.json"
    inner_json = custom_dir / ".claude.json"

    # Unparseable home file.
    home_json.write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert await _migration(agent_bundle).heal() == []
    assert home_json.read_text() == "{not json"
    assert not inner_json.exists()
    assert any(str(home_json) in r.getMessage() for r in caplog.records)

    # Parseable home entry, unparseable destination: neither file changes.
    caplog.clear()
    home_json.write_text(json.dumps({"mcpServers": {"coffer": _entry(custom.uid)}}))
    home_before = home_json.read_bytes()
    inner_json.write_text("{broken", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert await _migration(agent_bundle).heal() == []
    assert home_json.read_bytes() == home_before
    assert inner_json.read_text() == "{broken"
    assert any(str(inner_json) in r.getMessage() for r in caplog.records)

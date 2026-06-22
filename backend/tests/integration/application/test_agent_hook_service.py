"""Integration tests for AgentHookService (install/uninstall/status).

Slice 6 — SessionStart/SessionEnd lifecycle hook install. Clones the
AgentMcpService coverage: install writes a coffer-hook entry (with the agent
name baked into args) into the agent's hooks file, keeps a ``.bak``, audits;
idempotent; uninstall removes only Coffer's entry; status reflects state.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from coffer.application.agent.hook_service import AgentHookService
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ShimNotFound
from coffer.infrastructure.agent.config_file_store import ConfigFileStore

pytestmark = pytest.mark.asyncio

HOOK = "/opt/coffer/coffer-hook"


async def _register_claude(bundle, home: pathlib.Path):
    (home / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    await bundle.svc.register(agent_type=AgentType.CLAUDE_CODE, name="cc", actor="cli")


async def _register_codex(bundle, home: pathlib.Path):
    (home / ".codex" / "skills").mkdir(parents=True, exist_ok=True)
    await bundle.svc.register(agent_type=AgentType.CODEX, name="cx", actor="cli")


async def test_status_false_when_absent(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    st = await agent_bundle.hook.status("cc")
    assert st.installed is False
    assert st.command is None


async def test_install_claude_writes_both_events_with_agent_arg(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

    st = await agent_bundle.hook.install("cc", actor="ui")
    assert st.installed is True
    assert st.command == f"{HOOK} --agent cc"

    data = json.loads(settings.read_text())
    assert data["theme"] == "dark"  # neighbouring config preserved
    # Claude Code installs SessionStart + SessionEnd.
    assert set(data["hooks"]) == {"SessionStart", "SessionEnd"}
    leaf = data["hooks"]["SessionStart"][0]["hooks"][0]
    assert leaf["command"] == f"{HOOK} --agent cc"
    assert (tmp_path / ".claude" / "settings.json.bak").exists()

    rows = await agent_bundle.audit.query(
        kind="agent", name="cc", event_type=AuditEventType.AGENT_HOOK_INSTALLED.value
    )
    assert len(rows) == 1
    assert rows[0].details.get("command") == f"{HOOK} --agent cc"


async def test_install_codex_session_start_only(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_codex(agent_bundle, tmp_path)
    st = await agent_bundle.hook.install("cx", actor="ui")
    assert st.installed is True
    data = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    # Codex has no SessionEnd event — only SessionStart is installed.
    assert set(data["hooks"]) == {"SessionStart"}
    assert (await agent_bundle.hook.status("cx")).installed is True


async def test_install_idempotent(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    await agent_bundle.hook.install("cc", actor="ui")
    await agent_bundle.hook.install("cc", actor="ui")
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert len(data["hooks"]["SessionStart"]) == 1
    assert (await agent_bundle.hook.status("cc")).installed is True


async def test_install_preserves_user_hook(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    user_group = {"matcher": "startup", "hooks": [{"type": "command", "command": "/usr/bin/mine"}]}
    settings.write_text(json.dumps({"hooks": {"SessionStart": [user_group]}}), encoding="utf-8")

    await agent_bundle.hook.install("cc", actor="ui")
    groups = json.loads(settings.read_text())["hooks"]["SessionStart"]
    cmds = [g["hooks"][0]["command"] for g in groups]
    assert "/usr/bin/mine" in cmds  # user hook untouched
    assert f"{HOOK} --agent cc" in cmds

    # Uninstall removes only Coffer's entry, leaves the user's.
    await agent_bundle.hook.uninstall("cc", actor="ui")
    groups = json.loads(settings.read_text())["hooks"]["SessionStart"]
    cmds = [g["hooks"][0]["command"] for g in groups]
    assert cmds == ["/usr/bin/mine"]


async def test_uninstall_removes_entry_and_audits(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    await agent_bundle.hook.install("cc", actor="ui")

    st = await agent_bundle.hook.uninstall("cc", actor="ui")
    assert st.installed is False
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "hooks" not in data  # fully cleaned
    rows = await agent_bundle.audit.query(
        kind="agent", name="cc", event_type=AuditEventType.AGENT_HOOK_UNINSTALLED.value
    )
    assert len(rows) == 1


async def test_uninstall_when_absent_is_noop(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    st = await agent_bundle.hook.uninstall("cc", actor="ui")
    assert st.installed is False
    assert not (tmp_path / ".claude" / "settings.json").exists()
    rows = await agent_bundle.audit.query(
        kind="agent", name="cc", event_type=AuditEventType.AGENT_HOOK_UNINSTALLED.value
    )
    assert rows == []


async def test_install_raises_when_hook_unresolvable(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)

    def _boom() -> str:
        raise ShimNotFound()

    svc = AgentHookService(
        agent_service=agent_bundle.svc,
        audit=agent_bundle.audit,
        store=ConfigFileStore(),
        hook_resolver=_boom,
    )
    with pytest.raises(ShimNotFound):
        await svc.install("cc", actor="ui")
    assert not (tmp_path / ".claude" / "settings.json").exists()


async def test_quoted_command_when_binary_has_spaces(agent_bundle, tmp_path, monkeypatch):
    """A binary path with spaces must be shell-quoted so the agent's shlex.split
    still resolves argv[0] to the coffer-hook basename (status stays True)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    svc = AgentHookService(
        agent_service=agent_bundle.svc,
        audit=agent_bundle.audit,
        store=ConfigFileStore(),
        hook_resolver=lambda: "/Apps/My App/coffer-hook",
    )
    st = await svc.install("cc", actor="ui")
    assert "'/Apps/My App/coffer-hook'" in st.command
    assert (await svc.status("cc")).installed is True

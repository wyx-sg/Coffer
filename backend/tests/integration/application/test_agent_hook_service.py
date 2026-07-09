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
from coffer.domain.workspace_errors import HookInstallUnsupported
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


# --- cursor flavor (ADR-041) ---------------------------------------------------


async def _register_cursor(bundle, home: pathlib.Path):
    (home / ".cursor" / "skills").mkdir(parents=True, exist_ok=True)
    await bundle.svc.register(agent_type=AgentType.CURSOR, name="cur", actor="cli")


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="install Coffer's session hook into Cursor"
)
async def test_install_cursor_writes_flat_entry_with_dialect_and_event(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_cursor(agent_bundle, tmp_path)
    hooks_file = tmp_path / ".cursor" / "hooks.json"

    st = await agent_bundle.hook.install("cur", actor="ui")
    assert st.installed is True
    # Cursor's stdin payload does not name the event, so it is baked into argv
    # alongside the dialect that selects the stdout envelope.
    assert st.command == f"{HOOK} --agent cur --dialect cursor --event sessionStart"

    data = json.loads(hooks_file.read_text())
    assert data["version"] == 1
    # Flat command entry, camelCase key — Cursor's shape, not Claude's.
    assert data["hooks"] == {"sessionStart": [{"command": st.command}]}


async def test_install_cursor_preserves_foreign_hooks(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_cursor(agent_bundle, tmp_path)
    hooks_file = tmp_path / ".cursor" / "hooks.json"
    hooks_file.write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {"beforeSubmitPrompt": [{"command": "/opt/other/hook.sh"}]},
            }
        ),
        encoding="utf-8",
    )

    await agent_bundle.hook.install("cur", actor="ui")
    data = json.loads(hooks_file.read_text())
    # A third party's hook for an unrelated event is untouched.
    assert data["hooks"]["beforeSubmitPrompt"] == [{"command": "/opt/other/hook.sh"}]
    assert "sessionStart" in data["hooks"]


async def test_cursor_install_idempotent_then_uninstall_restores(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_cursor(agent_bundle, tmp_path)
    hooks_file = tmp_path / ".cursor" / "hooks.json"

    await agent_bundle.hook.install("cur", actor="ui")
    await agent_bundle.hook.install("cur", actor="ui")
    entries = json.loads(hooks_file.read_text())["hooks"]["sessionStart"]
    assert len(entries) == 1

    st = await agent_bundle.hook.uninstall("cur", actor="ui")
    assert st.installed is False
    assert "hooks" not in json.loads(hooks_file.read_text())
    assert (await agent_bundle.hook.status("cur")).installed is False


async def test_opencode_hook_install_unsupported(agent_bundle, tmp_path, monkeypatch):
    # opencode declares no context_injection: status is "not installed", never an
    # error; install rejects with 422 rather than writing anything.
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".config" / "opencode" / "skills").mkdir(parents=True, exist_ok=True)
    await agent_bundle.svc.register(agent_type=AgentType.OPENCODE, name="oc", actor="cli")

    st = await agent_bundle.hook.status("oc")
    assert st.installed is False
    # Surfaces read `supported` to disable the control up front — status never
    # raises, so a surface waiting for a 422 would render a control that 422s.
    assert st.supported is False
    with pytest.raises(HookInstallUnsupported):
        await agent_bundle.hook.install("oc", actor="ui")


async def test_supported_true_for_agents_with_shell_injection(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    await _register_cursor(agent_bundle, tmp_path)
    assert (await agent_bundle.hook.status("cc")).supported is True
    assert (await agent_bundle.hook.status("cur")).supported is True

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


# --- cursor flavor (ADR-042) ---------------------------------------------------


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


async def test_supported_true_for_agents_with_shell_injection(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_claude(agent_bundle, tmp_path)
    await _register_cursor(agent_bundle, tmp_path)
    assert (await agent_bundle.hook.status("cc")).supported is True
    assert (await agent_bundle.hook.status("cur")).supported is True


# --- opencode plugin drop (ADR-042 PLUGIN_DROP) ---------------------------------


async def _register_opencode(bundle, home: pathlib.Path):
    (home / ".config" / "opencode" / "skills").mkdir(parents=True, exist_ok=True)
    await bundle.svc.register(agent_type=AgentType.OPENCODE, name="oc", actor="cli")


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="install Coffer's session-context plugin into opencode"
)
async def test_install_opencode_drops_plugin_file(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_opencode(agent_bundle, tmp_path)
    plugin_file = tmp_path / ".config" / "opencode" / "plugin" / "coffer-session-context.js"

    st = await agent_bundle.hook.install("oc", actor="ui")
    assert st.installed is True
    assert st.command == "/opt/coffer/coffer-hook --agent oc --dialect raw --event sessionStart"

    text = plugin_file.read_text()
    assert text.startswith("// coffer:session-context")
    assert '"--dialect", "raw"' in text
    assert 'const AGENT = "oc";' in text

    rows = await agent_bundle.audit.query(
        kind="agent", name="oc", event_type=AuditEventType.AGENT_HOOK_INSTALLED.value
    )
    assert len(rows) == 1
    assert rows[0].details.get("path") == str(plugin_file)

    st = await agent_bundle.hook.status("oc")
    assert st.installed is True
    assert st.supported is True
    assert st.command is not None

    # Reinstall overwrites Coffer's own file in place — still exactly one file.
    await agent_bundle.hook.install("oc", actor="ui")
    siblings = list(plugin_file.parent.glob("*.js"))
    assert siblings == [plugin_file]


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="uninstalling the opencode plugin removes only Coffer's file",
)
async def test_uninstall_opencode_removes_only_coffer_plugin(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_opencode(agent_bundle, tmp_path)
    plugin_dir = tmp_path / ".config" / "opencode" / "plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "user-plugin.js").write_text("export const Mine = async () => ({});\n")

    await agent_bundle.hook.install("oc", actor="ui")
    st = await agent_bundle.hook.uninstall("oc", actor="ui")
    assert st.installed is False
    assert not (plugin_dir / "coffer-session-context.js").exists()
    assert (plugin_dir / "user-plugin.js").exists()  # never touched

    rows = await agent_bundle.audit.query(
        kind="agent", name="oc", event_type=AuditEventType.AGENT_HOOK_UNINSTALLED.value
    )
    assert len(rows) == 1
    # Uninstalling again is a no-op success that audits nothing further.
    await agent_bundle.hook.uninstall("oc", actor="ui")
    rows = await agent_bundle.audit.query(
        kind="agent", name="oc", event_type=AuditEventType.AGENT_HOOK_UNINSTALLED.value
    )
    assert len(rows) == 1


async def test_opencode_install_raises_when_hook_unresolvable(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_opencode(agent_bundle, tmp_path)

    def _boom() -> str:
        raise ShimNotFound()

    svc = AgentHookService(
        agent_service=agent_bundle.svc,
        audit=agent_bundle.audit,
        store=ConfigFileStore(),
        hook_resolver=_boom,
    )
    with pytest.raises(ShimNotFound):
        await svc.install("oc", actor="ui")
    assert not (tmp_path / ".config" / "opencode" / "plugin").exists()


# --- hermes instructions block (ADR-042 INSTRUCTIONS_BLOCK) ---------------------


async def _register_hermes(bundle, home: pathlib.Path):
    (home / ".hermes" / "skills").mkdir(parents=True, exist_ok=True)
    await bundle.svc.register(agent_type=AgentType.HERMES, name="hm", actor="cli")


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="install Coffer's session-context block into Hermes"
)
async def test_install_hermes_renders_block_into_soul_md(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_hermes(agent_bundle, tmp_path)
    soul_md = tmp_path / ".hermes" / "SOUL.md"
    soul_md.write_text("# My hermes persona\n", encoding="utf-8")

    st = await agent_bundle.hook.install("hm", actor="ui")
    assert st.installed is True
    assert st.command is None  # a block carries the payload itself, no command

    text = soul_md.read_text()
    assert text.startswith("# My hermes persona")  # user content preserved
    assert "coffer:session-context:start" in text
    assert "RULES BUNDLE" in text  # the FR-044 payload, rendered at install time
    assert (tmp_path / ".hermes" / "SOUL.md.bak").exists()

    rows = await agent_bundle.audit.query(
        kind="agent", name="hm", event_type=AuditEventType.AGENT_HOOK_INSTALLED.value
    )
    assert len(rows) == 1
    assert (await agent_bundle.hook.status("hm")).installed is True
    assert (await agent_bundle.hook.status("hm")).supported is True


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="uninstalling the Hermes context block is a true inverse"
)
async def test_uninstall_hermes_block_restores_user_document(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_hermes(agent_bundle, tmp_path)
    soul_md = tmp_path / ".hermes" / "SOUL.md"
    original = "# My hermes persona\n\nAnswer in French.\n"
    soul_md.write_text(original, encoding="utf-8")

    await agent_bundle.hook.install("hm", actor="ui")
    st = await agent_bundle.hook.uninstall("hm", actor="ui")
    assert st.installed is False
    assert soul_md.read_text() == original

    rows = await agent_bundle.audit.query(
        kind="agent", name="hm", event_type=AuditEventType.AGENT_HOOK_UNINSTALLED.value
    )
    assert len(rows) == 1
    # Uninstalling again is a no-op success that writes and audits nothing.
    await agent_bundle.hook.uninstall("hm", actor="ui")
    rows = await agent_bundle.audit.query(
        kind="agent", name="hm", event_type=AuditEventType.AGENT_HOOK_UNINSTALLED.value
    )
    assert len(rows) == 1


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="a Coffer-driven turn refreshes the Hermes context block"
)
async def test_refresh_blocks_rerenders_installed_hermes_agents(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_hermes(agent_bundle, tmp_path)
    soul_md = tmp_path / ".hermes" / "SOUL.md"
    await agent_bundle.hook.install("hm", actor="ui")

    # The payload changes between turns (new rules/memory); the pre-turn refresh
    # re-renders the block in place without a new audit event.
    agent_bundle.hook._session_context = _fresh_payload
    refreshed = await agent_bundle.hook.refresh_blocks_for_type(AgentType.HERMES)
    assert refreshed == 1
    text = soul_md.read_text()
    assert "FRESH BUNDLE" in text
    assert "RULES BUNDLE" not in text
    assert text.count("coffer:session-context:start") == 1
    rows = await agent_bundle.audit.query(
        kind="agent", name="hm", event_type=AuditEventType.AGENT_HOOK_INSTALLED.value
    )
    assert len(rows) == 1  # refresh does not audit


async def _fresh_payload() -> str:
    return "FRESH BUNDLE"


async def test_refresh_skips_agents_without_an_installed_block(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_hermes(agent_bundle, tmp_path)  # registered but not installed
    assert await agent_bundle.hook.refresh_blocks_for_type(AgentType.HERMES) == 0
    assert not (tmp_path / ".hermes" / "SOUL.md").exists()


async def test_install_creates_soul_md_when_absent(agent_bundle, tmp_path, monkeypatch):
    # A fresh hermes has no SOUL.md yet — install creates the file holding just
    # the block (no .bak: there was no prior version to keep).
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_hermes(agent_bundle, tmp_path)
    st = await agent_bundle.hook.install("hm", actor="ui")
    assert st.installed is True
    soul_md = tmp_path / ".hermes" / "SOUL.md"
    assert soul_md.exists()
    assert "RULES BUNDLE" in soul_md.read_text()


async def test_refresh_with_unchanged_payload_writes_nothing(agent_bundle, tmp_path, monkeypatch):
    # The `new_text != text` guard: an unchanged bundle must not churn the
    # file's mtime / .bak every turn.
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_hermes(agent_bundle, tmp_path)
    soul_md = tmp_path / ".hermes" / "SOUL.md"
    await agent_bundle.hook.install("hm", actor="ui")
    before = soul_md.stat().st_mtime_ns
    assert await agent_bundle.hook.refresh_blocks_for_type(AgentType.HERMES) == 1
    assert soul_md.stat().st_mtime_ns == before


async def test_block_mode_unsupported_without_a_payload_source(agent_bundle, tmp_path, monkeypatch):
    # A service wired without `session_context` cannot render the block: the
    # facet degrades to unsupported (status false, install 422), matching how
    # PLUGIN_DROP is treated — never a control that fails on click.
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_hermes(agent_bundle, tmp_path)
    svc = AgentHookService(
        agent_service=agent_bundle.svc,
        audit=agent_bundle.audit,
        store=ConfigFileStore(),
        hook_resolver=lambda: "/opt/coffer/coffer-hook",
    )
    st = await svc.status("hm")
    assert st.installed is False
    assert st.supported is False
    with pytest.raises(HookInstallUnsupported):
        await svc.install("hm", actor="ui")
    assert await svc.refresh_blocks_for_type(AgentType.HERMES) == 0


# --- openclaw plugin package (ADR-043 PLUGIN_DROP, openclaw flavor) ---------------


async def _register_openclaw(bundle, home: pathlib.Path):
    (home / ".openclaw" / "skills").mkdir(parents=True, exist_ok=True)
    await bundle.svc.register(agent_type=AgentType.OPENCLAW, name="ow", actor="cli")


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="install Coffer's session-context plugin package into OpenClaw",
)
async def test_install_openclaw_drops_package_and_enables_entry(
    agent_bundle, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_openclaw(agent_bundle, tmp_path)
    package_dir = tmp_path / ".openclaw" / "extensions" / "coffer-session-context"
    config = tmp_path / ".openclaw" / "openclaw.json"
    config.write_text(json.dumps({"gateway": {"port": 18789}}), encoding="utf-8")

    st = await agent_bundle.hook.install("ow", actor="ui")
    assert st.installed is True
    assert st.command == "/opt/coffer/coffer-hook --agent ow --dialect raw --event sessionStart"

    # The three package files land under extensions/<id>/.
    assert (package_dir / "package.json").exists()
    assert (package_dir / "openclaw.plugin.json").exists()
    entry = (package_dir / "index.js").read_text()
    assert entry.startswith("// coffer:session-context")
    assert 'const AGENT = "ow";' in entry
    assert "before_prompt_build" in entry

    # Non-bundled plugins are fail-closed — install also flips the enable flag,
    # preserving the user's other config.
    data = json.loads(config.read_text())
    assert data["plugins"]["entries"]["coffer-session-context"] == {"enabled": True}
    assert data["gateway"] == {"port": 18789}

    rows = await agent_bundle.audit.query(
        kind="agent", name="ow", event_type=AuditEventType.AGENT_HOOK_INSTALLED.value
    )
    assert len(rows) == 1
    assert rows[0].details.get("path") == str(package_dir)

    st = await agent_bundle.hook.status("ow")
    assert st.installed is True
    assert st.supported is True
    assert st.command is not None

    # Reinstall overwrites Coffer's own package in place — same three files.
    await agent_bundle.hook.install("ow", actor="ui")
    names = sorted(p.name for p in package_dir.iterdir() if not p.name.endswith(".bak"))
    assert names == ["index.js", "openclaw.plugin.json", "package.json"]


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="uninstalling the OpenClaw plugin package removes the extension and its enable flag",
)
async def test_uninstall_openclaw_removes_package_and_entry(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_openclaw(agent_bundle, tmp_path)
    extensions = tmp_path / ".openclaw" / "extensions"
    extensions.mkdir(parents=True, exist_ok=True)
    (extensions / "user-ext").mkdir()
    (extensions / "user-ext" / "package.json").write_text("{}\n")
    config = tmp_path / ".openclaw" / "openclaw.json"
    config.write_text(
        json.dumps({"plugins": {"entries": {"memory-core": {"enabled": False}}}}),
        encoding="utf-8",
    )

    await agent_bundle.hook.install("ow", actor="ui")
    st = await agent_bundle.hook.uninstall("ow", actor="ui")
    assert st.installed is False
    # The whole package dir is gone; the user's own extension is untouched.
    assert not (extensions / "coffer-session-context").exists()
    assert (extensions / "user-ext" / "package.json").exists()
    # Coffer's entries key is gone; the user's other entry survives.
    data = json.loads(config.read_text())
    assert "coffer-session-context" not in data["plugins"]["entries"]
    assert data["plugins"]["entries"]["memory-core"] == {"enabled": False}
    assert (await agent_bundle.hook.status("ow")).installed is False

    rows = await agent_bundle.audit.query(
        kind="agent", name="ow", event_type=AuditEventType.AGENT_HOOK_UNINSTALLED.value
    )
    assert len(rows) == 1
    # Uninstalling again is a no-op success that audits nothing further (and
    # does not rewrite the config file).
    before = config.read_text()
    await agent_bundle.hook.uninstall("ow", actor="ui")
    rows = await agent_bundle.audit.query(
        kind="agent", name="ow", event_type=AuditEventType.AGENT_HOOK_UNINSTALLED.value
    )
    assert len(rows) == 1
    assert config.read_text() == before


async def test_openclaw_install_raises_when_hook_unresolvable(agent_bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    await _register_openclaw(agent_bundle, tmp_path)

    def _boom() -> str:
        raise ShimNotFound()

    svc = AgentHookService(
        agent_service=agent_bundle.svc,
        audit=agent_bundle.audit,
        store=ConfigFileStore(),
        hook_resolver=_boom,
    )
    with pytest.raises(ShimNotFound):
        await svc.install("ow", actor="ui")
    assert not (tmp_path / ".openclaw" / "extensions").exists()

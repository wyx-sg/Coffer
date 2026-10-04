"""Every hook in an agent's native config, read only (spec agent-registry
"List every hook in the agent's native config").

Real SQLite registry and audit log, real config files in fake agent
directories; only the plugin listing is a stand-in, handing back a plugin
package the test lays out on disk.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

import pytest

from coffer.application.agent.hooks_service import AgentHooksService
from coffer.application.agent.plugin_views import PluginDetailView, PluginsOut, PluginView
from coffer.domain.agent.hooks import HookHealth, HookSource
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.hook_trust import HookTrust
from coffer.domain.memory.delivery import DELIVERY_EVENTS, MARKER, DeliveryAdapter, events_label
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.memory.delivery.codex import current_hash, trust_key
from tests.integration.application.conftest import AgentTestBundle
from tests.support.facets import agent_catalog
from tests.support.homes import IsolatedHome, fake_agent_dir


@dataclass
class _Plugins:
    """One installed plugin per entry: (id, enabled, package root)."""

    installed: list[tuple[str, bool, pathlib.Path]]

    async def list_plugins(self, uid: str) -> PluginsOut:
        return PluginsOut(
            items=[
                PluginView(id=pid, name=pid, marketplace="m", enabled=on, cache_present=True)
                for pid, on, _root in self.installed
            ],
            marketplaces=[],
            parse_errors=[],
        )

    async def get_plugin(self, uid: str, plugin_id: str) -> PluginDetailView:
        pid, on, root = next(p for p in self.installed if p[0] == plugin_id)
        view = PluginView(id=pid, name=pid, marketplace="m", enabled=on, cache_present=True)
        return PluginDetailView(
            plugin=view,
            marketplace_source_type=None,
            marketplace_source=None,
            install_path=str(root),
            can_uninstall=False,
            contents=None,
        )


def _hooks(event: str, command: str, matcher: str | None = None) -> str:
    group: dict[str, object] = {"hooks": [{"type": "command", "command": command}]}
    if matcher is not None:
        group["matcher"] = matcher
    return json.dumps({"hooks": {event: [group]}})


def _adapter(agent_type: AgentType) -> DeliveryAdapter:
    adapter = agent_catalog().delivery_hook(agent_type)
    assert adapter is not None
    return adapter


#: A marked Codex command other than the one Coffer writes now: bare `coffer`
#: rather than the CLI's absolute path.
def _stale_codex_command(uid: str) -> str:
    return f': {MARKER}; coffer memory hook --agent-uid {uid} --cwd "$PWD"'


def _service(bundle: AgentTestBundle, plugins: _Plugins | None = None) -> AgentHooksService:
    return AgentHooksService(
        agent_service=bundle.svc,
        store=ConfigFileStore(),
        plugins=plugins or _Plugins([]),
        audit=bundle.audit,
        catalog=agent_catalog(),
    )


@pytest.mark.acceptance(
    spec="agent-registry", scenario="list an agent's hooks with Coffer's own marked"
)
@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="read Claude Code hooks from both settings files and an enabled plugin",
)
async def test_hooks_from_settings_and_plugins_with_coffers_own_current(
    agent_bundle: AgentTestBundle, isolated_home: IsolatedHome, tmp_path: pathlib.Path
) -> None:
    claude = fake_agent_dir(isolated_home, AgentType.CLAUDE_CODE)
    agent = await agent_bundle.svc.register(
        agent_type=AgentType.CLAUDE_CODE, config_dir=None, actor="t"
    )
    own = _adapter(AgentType.CLAUDE_CODE).install(
        _hooks("PreToolUse", "lint.sh", "Bash"), agent.uid
    )
    claude.write("settings", own)
    claude.write("settings_local", _hooks("Stop", "notify.sh"))
    plugin_root = tmp_path / "plugin-pkg"
    (plugin_root / "hooks").mkdir(parents=True)
    (plugin_root / "hooks" / "hooks.json").write_text(_hooks("SessionStart", "plug.sh"))
    off_root = tmp_path / "off-pkg"
    (off_root / "hooks").mkdir(parents=True)
    (off_root / "hooks" / "hooks.json").write_text(_hooks("Stop", "never.sh"))
    before = claude.path("settings").read_text()

    out = await _service(
        agent_bundle, _Plugins([("p@m", True, plugin_root), ("off@m", False, off_root)])
    ).list_hooks(agent.uid)

    rows = {(h.event, h.command): h for h in out.items}
    assert rows[("PreToolUse", "lint.sh")].matcher == "Bash"
    assert rows[("PreToolUse", "lint.sh")].source is HookSource.USER
    assert rows[("Stop", "notify.sh")].path == str(claude.path("settings_local"))
    plugin_hook = rows[("SessionStart", "plug.sh")]
    assert plugin_hook.source is HookSource.PLUGIN and plugin_hook.plugin == "p@m"
    assert ("Stop", "never.sh") not in rows, "a disabled plugin's hooks do not run"
    mine = [h for h in out.items if h.coffer]
    assert sorted(h.event for h in mine) == sorted(DELIVERY_EVENTS)
    assert out.coffer_hook is not None
    assert out.coffer_hook.event == events_label(DELIVERY_EVENTS)
    assert out.coffer_hook.health is HookHealth.CURRENT
    assert out.coffer_hook.trust is HookTrust.NOT_REQUIRED
    assert out.coffer_hook.last_fired_at is None
    # Read only: nothing written, nothing audited.
    assert claude.path("settings").read_text() == before
    assert await agent_bundle.audit.query(event_type="memory_delivery_installed") == []


@pytest.mark.acceptance(spec="agent-registry", scenario="report a stale Coffer hook")
@pytest.mark.acceptance(spec="agent-registry/codex", scenario="read Codex hooks from hooks.json")
async def test_a_marked_hook_with_an_old_command_is_stale_and_fired_time_is_read(
    agent_bundle: AgentTestBundle, isolated_home: IsolatedHome
) -> None:
    codex = fake_agent_dir(isolated_home, AgentType.CODEX)
    agent = await agent_bundle.svc.register(agent_type=AgentType.CODEX, config_dir=None, actor="t")
    stale = {"type": "command", "command": _stale_codex_command(agent.uid), "timeout": 10}
    codex.write("hooks", json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [stale]}]}}))
    await agent_bundle.audit.record(
        AuditEventType.MEMORY_DELIVERY_FIRED.value, resource=agent, actor="cx"
    )

    out = await _service(agent_bundle).list_hooks(agent.uid)

    assert out.coffer_hook is not None
    assert out.coffer_hook.event == "UserPromptSubmit"
    assert out.coffer_hook.health is HookHealth.STALE
    assert out.coffer_hook.installed_command != out.coffer_hook.expected_command
    assert out.coffer_hook.trust is HookTrust.UNTRUSTED
    assert out.coffer_hook.last_fired_at is not None
    assert [(h.coffer, h.source, h.path) for h in out.items] == [
        (True, HookSource.USER, str(codex.path("hooks")))
    ]


async def test_a_missing_hook_and_an_unparseable_file_are_reported(
    agent_bundle: AgentTestBundle, isolated_home: IsolatedHome
) -> None:
    claude = fake_agent_dir(isolated_home, AgentType.CLAUDE_CODE)
    agent = await agent_bundle.svc.register(
        agent_type=AgentType.CLAUDE_CODE, config_dir=None, actor="t"
    )
    claude.write("settings", "{broken")
    claude.write("settings_local", _hooks("Stop", "notify.sh"))

    out = await _service(agent_bundle).list_hooks(agent.uid)

    assert [h.command for h in out.items] == ["notify.sh"]
    assert [e.source for e in out.parse_errors] == ["settings"]
    assert out.coffer_hook is not None and out.coffer_hook.health is HookHealth.MISSING


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="report whether Codex trusts Coffer's hook"
)
async def test_codex_trust_is_read_from_config_toml_and_never_written(
    agent_bundle: AgentTestBundle, isolated_home: IsolatedHome
) -> None:
    """A current Codex hook is ``untrusted`` until the user approves it, then
    ``trusted`` for exactly that definition, and ``modified`` once Coffer's
    command changes — read from ``[hooks.state]`` in ``config.toml``, which
    the listing never writes."""
    codex = fake_agent_dir(isolated_home, AgentType.CODEX)
    agent = await agent_bundle.svc.register(agent_type=AgentType.CODEX, config_dir=None, actor="t")
    adapter = _adapter(AgentType.CODEX)
    hooks_path = codex.write("hooks", adapter.install("", agent.uid))
    config = codex.write("config", 'model = "gpt-5"\n')

    out = await _service(agent_bundle).list_hooks(agent.uid)
    assert out.coffer_hook is not None
    assert out.coffer_hook.event == events_label(DELIVERY_EVENTS)
    assert out.coffer_hook.health is HookHealth.CURRENT
    assert out.coffer_hook.trust is HookTrust.UNTRUSTED

    # The user approves each entry in Codex's /hooks: Codex records each hash.
    hooks = adapter.find_all(hooks_path.read_text())
    assert len(hooks) == len(DELIVERY_EVENTS)
    states = [
        f'[hooks.state."{trust_key(str(hooks_path), h)}"]\ntrusted_hash = "{current_hash(h)}"\n'
        for h in hooks
    ]
    # Approving only some of the four still leaves Coffer's hook untrusted.
    config.write_text('model = "gpt-5"\n\n' + "\n".join(states[:-1]))
    out = await _service(agent_bundle).list_hooks(agent.uid)
    assert out.coffer_hook is not None and out.coffer_hook.trust is HookTrust.UNTRUSTED
    approved = 'model = "gpt-5"\n\n' + "\n".join(states)
    config.write_text(approved)
    out = await _service(agent_bundle).list_hooks(agent.uid)
    assert out.coffer_hook is not None and out.coffer_hook.trust is HookTrust.TRUSTED

    # A later build changes one entry's command: that approval no longer matches.
    hooks_path.write_text(
        hooks_path.read_text().replace('--cwd \\"$PWD\\"', '--cwd \\"$PWD\\" ', 1)
    )
    out = await _service(agent_bundle).list_hooks(agent.uid)
    assert out.coffer_hook is not None and out.coffer_hook.trust is HookTrust.MODIFIED
    assert config.read_text() == approved

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
from coffer.domain.agent.hooks import HookSource
from coffer.domain.agent.types import AgentType
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from tests.integration.application.conftest import AgentTestBundle
from tests.support.facets import agent_catalog
from tests.support.homes import IsolatedHome, fake_agent_dir


@dataclass
class _Plugins:
    """One installed plugin per entry: (id, enabled, package root)."""

    installed: list[tuple[str, bool, pathlib.Path]]

    async def enabled_install_roots(self, uid: str) -> list[tuple[str, str]]:
        return [(pid, str(root)) for pid, on, root in self.installed if on]


def _hooks(event: str, command: str, matcher: str | None = None) -> str:
    group: dict[str, object] = {"hooks": [{"type": "command", "command": command}]}
    if matcher is not None:
        group["matcher"] = matcher
    return json.dumps({"hooks": {event: [group]}})


def _service(bundle: AgentTestBundle, plugins: _Plugins | None = None) -> AgentHooksService:
    return AgentHooksService(
        agent_service=bundle.svc,
        store=ConfigFileStore(),
        plugins=plugins or _Plugins([]),
        catalog=agent_catalog(),
    )


@pytest.mark.acceptance(spec="agent-registry", scenario="list an agent's hooks")
@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="read Claude Code hooks from both settings files and an enabled plugin",
)
async def test_hooks_from_settings_and_plugins(
    agent_bundle: AgentTestBundle, isolated_home: IsolatedHome, tmp_path: pathlib.Path
) -> None:
    claude = fake_agent_dir(isolated_home, AgentType.CLAUDE_CODE)
    agent = await agent_bundle.svc.register(
        agent_type=AgentType.CLAUDE_CODE, config_dir=None, actor="t"
    )
    claude.write("settings", _hooks("PreToolUse", "lint.sh", "Bash"))
    claude.write("settings_local", _hooks("Stop", "notify.sh"))
    plugin_root = tmp_path / "plugin-pkg"
    (plugin_root / "hooks").mkdir(parents=True)
    (plugin_root / "hooks" / "hooks.json").write_text(_hooks("SessionStart", "plug.sh"))
    off_root = tmp_path / "off-pkg"
    (off_root / "hooks").mkdir(parents=True)
    (off_root / "hooks" / "hooks.json").write_text(_hooks("Stop", "never.sh"))
    before = claude.path("settings").read_text()
    events_before = await agent_bundle.audit.query()

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
    # Read only: nothing written, nothing audited.
    assert claude.path("settings").read_text() == before
    assert await agent_bundle.audit.query() == events_before


@pytest.mark.acceptance(spec="agent-registry/codex", scenario="read Codex hooks from hooks.json")
async def test_codex_hooks_are_read_from_hooks_json(
    agent_bundle: AgentTestBundle, isolated_home: IsolatedHome
) -> None:
    codex = fake_agent_dir(isolated_home, AgentType.CODEX)
    agent = await agent_bundle.svc.register(agent_type=AgentType.CODEX, config_dir=None, actor="t")
    codex.write("hooks", _hooks("UserPromptSubmit", "remind.sh"))

    out = await _service(agent_bundle).list_hooks(agent.uid)

    assert [(h.event, h.command, h.source, h.path) for h in out.items] == [
        ("UserPromptSubmit", "remind.sh", HookSource.USER, str(codex.path("hooks")))
    ]


async def test_an_unparseable_file_is_reported_beside_the_others(
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

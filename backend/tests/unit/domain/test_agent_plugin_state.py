import json

import pytest

from coffer.domain.agent import plugin_state as ps
from coffer.domain.workspace_errors import AgentConfigParseError, PluginNotFound

CODEX_TOML = """
[marketplaces.openai-curated]
source_type = "remote"
source = "https://example/curated"

[plugins."gmail@openai-curated"]
enabled = true

[plugins."superpowers@openai-curated"]
enabled = false
"""

CLAUDE_INSTALLED = (
    '{"version": 2, "plugins": {"superpowers@claude-plugins-official": [{}], '
    '"warp@claude-code-warp": [{}]}}'
)
CLAUDE_MARKETPLACES = (
    '{"claude-plugins-official": {"source": {"source": "github", '
    '"repo": "anthropics/claude-plugins-official"}}, '
    '"claude-code-warp": {"source": {"source": "github", "repo": "warpdotdev/claude-code-warp"}}}'
)
CLAUDE_SETTINGS = (
    '{"enabledPlugins": {"superpowers@claude-plugins-official": true, '
    '"warp@claude-code-warp": false}}'
)


def test_parse_codex_plugins() -> None:
    plugins, marketplaces = ps.parse_codex(CODEX_TOML)
    assert {p.id: p.enabled for p in plugins} == {
        "gmail@openai-curated": True,
        "superpowers@openai-curated": False,
    }
    gmail = next(p for p in plugins if p.id == "gmail@openai-curated")
    assert gmail.name == "gmail" and gmail.marketplace == "openai-curated"
    assert [m.name for m in marketplaces] == ["openai-curated"]
    assert marketplaces[0].source == "https://example/curated"


def test_parse_codex_enabled_defaults_true() -> None:
    plugins, _ = ps.parse_codex('[plugins."x@m"]\n')
    assert plugins[0].enabled is True


def test_parse_codex_parse_error() -> None:
    with pytest.raises(AgentConfigParseError):
        ps.parse_codex("[plugins\nbroken")


def test_toggle_codex_plugin() -> None:
    out = ps.set_codex_enabled(CODEX_TOML, "superpowers@openai-curated", True)
    plugins, _ = ps.parse_codex(out)
    assert {p.id: p.enabled for p in plugins}["superpowers@openai-curated"] is True
    assert "source_type" in out  # sibling content survives the round-trip
    with pytest.raises(PluginNotFound):
        ps.set_codex_enabled(CODEX_TOML, "ghost@x", True)


def test_remove_codex_plugin_entry() -> None:
    out = ps.remove_codex_entry(CODEX_TOML, "gmail@openai-curated")
    plugins, _ = ps.parse_codex(out)
    assert "gmail@openai-curated" not in {p.id for p in plugins}
    with pytest.raises(PluginNotFound):
        ps.remove_codex_entry(CODEX_TOML, "ghost@x")


def test_parse_claude_plugins() -> None:
    plugins, marketplaces = ps.parse_claude(
        installed_json=CLAUDE_INSTALLED,
        marketplaces_json=CLAUDE_MARKETPLACES,
        settings_json=CLAUDE_SETTINGS,
    )
    assert {p.id: p.enabled for p in plugins} == {
        "superpowers@claude-plugins-official": True,
        "warp@claude-code-warp": False,
    }
    assert {m.name for m in marketplaces} == {"claude-plugins-official", "claude-code-warp"}


def test_parse_claude_union_includes_settings_only_ids() -> None:
    # a plugin present only in enabledPlugins still shows up (install state is elsewhere)
    plugins, _ = ps.parse_claude(
        installed_json="{}",
        marketplaces_json="{}",
        settings_json='{"enabledPlugins": {"solo@mkt": false}}',
    )
    assert [(p.id, p.enabled) for p in plugins] == [("solo@mkt", False)]


def test_parse_claude_missing_files_tolerated() -> None:
    plugins, marketplaces = ps.parse_claude(
        installed_json=None, marketplaces_json=None, settings_json=None
    )
    assert plugins == [] and marketplaces == []


def test_parse_claude_enabled_defaults_true_for_installed() -> None:
    plugins, _ = ps.parse_claude(
        installed_json=CLAUDE_INSTALLED, marketplaces_json="{}", settings_json="{}"
    )
    assert all(p.enabled for p in plugins)


def test_toggle_claude_plugin_writes_settings_only() -> None:
    out = ps.set_claude_enabled(CLAUDE_SETTINGS, "warp@claude-code-warp", True)
    assert json.loads(out)["enabledPlugins"]["warp@claude-code-warp"] is True
    out2 = ps.set_claude_enabled("{}", "new@mkt", False)
    assert json.loads(out2)["enabledPlugins"]["new@mkt"] is False
    out3 = ps.set_claude_enabled("", "new@mkt", True)  # settings.json may not exist yet
    assert json.loads(out3)["enabledPlugins"]["new@mkt"] is True


def test_toggle_claude_tolerates_non_dict_enabled_map() -> None:
    out = ps.set_claude_enabled('{"enabledPlugins": ["broken"]}', "x@m", True)
    assert json.loads(out)["enabledPlugins"] == {"x@m": True}

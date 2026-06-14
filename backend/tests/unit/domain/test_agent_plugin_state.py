import json

import pytest

from coffer.domain.agent import plugin_state as ps
from coffer.domain.agent import plugin_state_extra as pse
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


# ---------------------------------------------------------------------------
# Cursor (read-only; VSIX extensions.json is a JSON array)
# ---------------------------------------------------------------------------

CURSOR_EXTENSIONS = json.dumps(
    [
        {"identifier": {"id": "ms-python.python"}, "version": "2024.1.0"},
        {"identifier": {"id": "esbenp.prettier-vscode"}, "version": "10.0.0"},
        {"version": "1.0.0"},  # malformed entry without identifier — tolerated
    ]
)


def test_parse_cursor_extensions() -> None:
    plugins, marketplaces = pse.parse_cursor(CURSOR_EXTENSIONS)
    assert [p.id for p in plugins] == ["ms-python.python", "esbenp.prettier-vscode"]
    # No marketplace concept for Cursor extensions.
    assert marketplaces == []
    # All listed extensions are reported enabled (enable/disable lives in SQLite).
    assert all(p.enabled for p in plugins)
    assert all(p.installed for p in plugins)


def test_parse_cursor_missing_tolerated() -> None:
    plugins, marketplaces = pse.parse_cursor(None)
    assert plugins == [] and marketplaces == []
    plugins, _ = pse.parse_cursor("")
    assert plugins == []


def test_parse_cursor_parse_error() -> None:
    with pytest.raises(AgentConfigParseError):
        pse.parse_cursor("{not json")


def test_parse_cursor_non_array_tolerated() -> None:
    # A non-array top level is treated as "no extensions" rather than a crash.
    plugins, _ = pse.parse_cursor('{"unexpected": true}')
    assert plugins == []


# ---------------------------------------------------------------------------
# OpenCode (toggle = presence in the "plugin" array)
# ---------------------------------------------------------------------------

OPENCODE_CONFIG = json.dumps({"plugin": ["my-plugin", "./local/plugin.ts"], "other": 1})


def test_parse_opencode_plugins() -> None:
    plugins, marketplaces = pse.parse_opencode(OPENCODE_CONFIG)
    assert [p.id for p in plugins] == ["my-plugin", "./local/plugin.ts"]
    assert marketplaces == []
    assert all(p.enabled for p in plugins)


def test_parse_opencode_missing_tolerated() -> None:
    plugins, _ = pse.parse_opencode("{}")
    assert plugins == []
    plugins, _ = pse.parse_opencode(None)
    assert plugins == []


def test_parse_opencode_parse_error() -> None:
    with pytest.raises(AgentConfigParseError):
        pse.parse_opencode("{broken")


def test_set_opencode_enabled_adds_and_removes() -> None:
    # Disable removes from the array.
    out = pse.set_opencode_enabled(OPENCODE_CONFIG, "my-plugin", False)
    plugins, _ = pse.parse_opencode(out)
    assert "my-plugin" not in {p.id for p in plugins}
    assert "other" in json.loads(out)  # sibling keys survive
    # Enable adds to the array.
    out2 = pse.set_opencode_enabled(out, "my-plugin", True)
    plugins2, _ = pse.parse_opencode(out2)
    assert "my-plugin" in {p.id for p in plugins2}


def test_set_opencode_enabled_disable_missing_raises() -> None:
    with pytest.raises(PluginNotFound):
        pse.set_opencode_enabled(OPENCODE_CONFIG, "ghost", False)


def test_set_opencode_enabled_idempotent_add() -> None:
    out = pse.set_opencode_enabled(OPENCODE_CONFIG, "my-plugin", True)
    # No duplicate appended.
    assert json.loads(out)["plugin"].count("my-plugin") == 1


def test_remove_opencode_entry() -> None:
    out = pse.remove_opencode_entry(OPENCODE_CONFIG, "my-plugin")
    plugins, _ = pse.parse_opencode(out)
    assert "my-plugin" not in {p.id for p in plugins}
    with pytest.raises(PluginNotFound):
        pse.remove_opencode_entry(OPENCODE_CONFIG, "ghost")


# ---------------------------------------------------------------------------
# OpenClaw (plugins{} block — tolerant of partly documented shape)
# ---------------------------------------------------------------------------

OPENCLAW_CONFIG = json.dumps(
    {
        "plugins": {
            "entries": ["alpha", "beta", "gamma"],
            "enabled": ["alpha", "beta"],
            "deny": ["gamma"],
        }
    }
)


def test_parse_openclaw_plugins() -> None:
    plugins, marketplaces = pse.parse_openclaw(OPENCLAW_CONFIG)
    by_id = {p.id: p.enabled for p in plugins}
    assert by_id == {"alpha": True, "beta": True, "gamma": False}
    assert marketplaces == []


def test_parse_openclaw_entries_as_dicts() -> None:
    text = json.dumps({"plugins": {"entries": [{"id": "x"}, {"name": "y"}], "enabled": ["x"]}})
    plugins, _ = pse.parse_openclaw(text)
    by_id = {p.id: p.enabled for p in plugins}
    assert set(by_id) == {"x", "y"}
    assert by_id["x"] is True


def test_parse_openclaw_missing_tolerated() -> None:
    plugins, _ = pse.parse_openclaw("{}")
    assert plugins == []
    plugins, _ = pse.parse_openclaw(None)
    assert plugins == []


def test_parse_openclaw_parse_error() -> None:
    with pytest.raises(AgentConfigParseError):
        pse.parse_openclaw("{broken")


def test_set_openclaw_enabled() -> None:
    out = pse.set_openclaw_enabled(OPENCLAW_CONFIG, "gamma", True)
    by_id = {p.id: p.enabled for p in pse.parse_openclaw(out)[0]}
    assert by_id["gamma"] is True
    out2 = pse.set_openclaw_enabled(out, "alpha", False)
    by_id2 = {p.id: p.enabled for p in pse.parse_openclaw(out2)[0]}
    assert by_id2["alpha"] is False
    with pytest.raises(PluginNotFound):
        pse.set_openclaw_enabled(OPENCLAW_CONFIG, "ghost", True)


def test_remove_openclaw_entry() -> None:
    out = pse.remove_openclaw_entry(OPENCLAW_CONFIG, "alpha")
    assert "alpha" not in {p.id for p in pse.parse_openclaw(out)[0]}
    with pytest.raises(PluginNotFound):
        pse.remove_openclaw_entry(OPENCLAW_CONFIG, "ghost")

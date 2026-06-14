"""Unit tests for the MCP entry parsing and text-transform helpers."""

from __future__ import annotations

import pytest

from coffer.domain.agent import mcp_entries as me
from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.workspace_errors import AgentConfigParseError, McpEntryNotFound

CLAUDE_JSON = (
    '{"mcpServers": {"coffer": {"command": "/bin/coffer-mcp-shim"}, '
    '"jira": {"command": "uvx", "args": ["mcp-jira"], '
    '"env": {"JIRA_API_TOKEN": "tok123", "JIRA_URL": "https://j"}}}}'
)

CODEX_TOML = """
[mcp_servers.coffer]
command = "/bin/coffer-mcp-shim"

[mcp_servers.gas]
url = "https://gas.example/mcp"
enabled = false
[mcp_servers.gas.http_headers]
Authorization = "Bearer abc"

[mcp_servers.local]
command = "npx"
args = ["-y", "some-mcp"]
"""


def test_parse_claude_entries() -> None:
    entries = me.parse_entries(ConfigFileFormat.JSON, CLAUDE_JSON, source="global")
    by_name = {e.name: e for e in entries}
    assert by_name["coffer"].is_coffer and by_name["coffer"].transport == "stdio"
    j = by_name["jira"]
    assert j.source == "global" and j.command == "uvx" and j.enabled is None
    assert j.args == ("mcp-jira",)
    assert j.env == {"JIRA_API_TOKEN": "tok123", "JIRA_URL": "https://j"}


def test_parse_codex_entries() -> None:
    entries = me.parse_entries(ConfigFileFormat.TOML, CODEX_TOML, source="config")
    by_name = {e.name: e for e in entries}
    assert by_name["gas"].transport == "http" and by_name["gas"].url == "https://gas.example/mcp"
    assert by_name["gas"].enabled is False
    assert by_name["gas"].headers == {"Authorization": "Bearer abc"}
    assert by_name["local"].enabled is True  # flag absent → enabled by default
    assert by_name["local"].transport == "stdio"


def test_parse_error_raises() -> None:
    with pytest.raises(AgentConfigParseError):
        me.parse_entries(ConfigFileFormat.JSON, "{not json", source="global")
    with pytest.raises(AgentConfigParseError):
        me.parse_entries(ConfigFileFormat.TOML, "[mcp_servers\nbroken", source="config")


def test_parse_empty_and_absent_section() -> None:
    assert me.parse_entries(ConfigFileFormat.JSON, "", source="global") == []
    assert me.parse_entries(ConfigFileFormat.JSON, "{}", source="global") == []
    assert me.parse_entries(ConfigFileFormat.TOML, "[other]\nx = 1\n", source="config") == []


def test_remove_entry_json_and_missing() -> None:
    out = me.remove_entry(ConfigFileFormat.JSON, CLAUDE_JSON, "jira")
    assert "jira" not in out and "coffer" in out
    with pytest.raises(McpEntryNotFound):
        me.remove_entry(ConfigFileFormat.JSON, CLAUDE_JSON, "ghost")


def test_remove_entry_toml_preserves_layout() -> None:
    out = me.remove_entry(ConfigFileFormat.TOML, CODEX_TOML, "local")
    assert "[mcp_servers.local]" not in out and "[mcp_servers.gas]" in out
    assert "Authorization" in out  # untouched sibling content survives round-trip


def test_set_enabled_toml() -> None:
    out = me.set_entry_enabled(CODEX_TOML, "gas", True)
    entries = me.parse_entries(ConfigFileFormat.TOML, out, source="config")
    assert {e.name: e.enabled for e in entries}["gas"] is True
    with pytest.raises(McpEntryNotFound):
        me.set_entry_enabled(CODEX_TOML, "ghost", True)


def test_secret_env_keys() -> None:
    entries = me.parse_entries(ConfigFileFormat.JSON, CLAUDE_JSON, source="global")
    jira = next(e for e in entries if e.name == "jira")
    assert me.secret_env_keys(jira.env) == ["JIRA_API_TOKEN"]
    assert me.secret_env_keys({"MY_PASSWORD": "x", "EMPTY_TOKEN": "", "URL": "u"}) == [
        "MY_PASSWORD"
    ]


def test_secret_env_keys_includes_authorization() -> None:
    """Authorization headers must be treated as secrets."""
    assert me.secret_env_keys({"Authorization": "Bearer x"}) == ["Authorization"]
    # Case-insensitive
    assert me.secret_env_keys({"authorization": "tok"}) == ["authorization"]
    # Empty value is NOT flagged
    assert me.secret_env_keys({"Authorization": ""}) == []


def test_to_transport_config_moves_secrets_to_refs() -> None:
    entries = me.parse_entries(ConfigFileFormat.JSON, CLAUDE_JSON, source="global")
    jira = next(e for e in entries if e.name == "jira")
    cfg = me.to_transport_config(jira, {"JIRA_API_TOKEN": "mcp/codex/jira/JIRA_API_TOKEN"})
    assert cfg == {
        "type": "stdio",
        "command": "uvx",
        "args": ["mcp-jira"],
        "env": {"JIRA_URL": "https://j"},
        "credential_refs": {"JIRA_API_TOKEN": "mcp/codex/jira/JIRA_API_TOKEN"},
    }


def test_to_transport_config_http() -> None:
    entries = me.parse_entries(ConfigFileFormat.TOML, CODEX_TOML, source="config")
    gas = next(e for e in entries if e.name == "gas")
    cfg = me.to_transport_config(gas, {"Authorization": "mcp/gas/Authorization"})
    assert cfg == {
        "type": "http",
        "url": "https://gas.example/mcp",
        "headers": {},
        "credential_refs": {"Authorization": "mcp/gas/Authorization"},
    }


def test_parse_tolerates_malformed_fields() -> None:
    text = '{"mcpServers": {"weird": {"command": "c", "env": "oops", "headers": 5, "args": "abc"}}}'
    [e] = me.parse_entries(ConfigFileFormat.JSON, text, source="global")
    assert e.env == {} and e.headers == {} and e.args == ()


def test_repr_hides_env_and_header_values() -> None:
    entries = me.parse_entries(ConfigFileFormat.JSON, CLAUDE_JSON, source="global")
    jira = next(e for e in entries if e.name == "jira")
    assert "tok123" not in repr(jira)


# --- new shapes: container_key, command-array, environment, YAML ---


def test_parse_opencode_mcp_container_array_and_environment() -> None:
    """OpenCode: container `mcp`, command as array (exe = first element),
    env under `environment`, explicit `enabled`, and `type` for remote."""
    text = (
        '{"mcp": {'
        '"fs": {"type": "local", "command": ["npx", "-y", "fs-mcp"], '
        '"environment": {"ROOT": "/tmp"}, "enabled": true}, '
        '"remote": {"type": "remote", "url": "https://x/mcp", "enabled": false}'
        "}}"
    )
    entries = me.parse_entries(ConfigFileFormat.JSON, text, source="config", container_key="mcp")
    fs = next(e for e in entries if e.name == "fs")
    assert fs.transport == "stdio"
    assert fs.command == "npx" and fs.args == ("-y", "fs-mcp")
    assert fs.env == {"ROOT": "/tmp"} and fs.enabled is True
    remote = next(e for e in entries if e.name == "remote")
    assert remote.transport == "http" and remote.enabled is False
    # default container `mcpServers` finds nothing here
    assert me.parse_entries(ConfigFileFormat.JSON, text, source="config") == []


def test_parse_yaml_hermes_mcp_servers() -> None:
    text = (
        "mcp_servers:\n"
        "  coffer:\n    command: /bin/coffer-mcp-shim\n"
        "  files:\n    command: npx\n    args: ['-y', 'server-filesystem']\n"
        "    enabled: false\n"
    )
    entries = me.parse_entries(ConfigFileFormat.YAML, text, source="config")
    assert {e.name for e in entries} == {"coffer", "files"}
    files = next(e for e in entries if e.name == "files")
    assert files.command == "npx" and files.args == ("-y", "server-filesystem")
    assert files.enabled is False
    assert next(e for e in entries if e.name == "coffer").is_coffer is True


def test_remove_entry_yaml_preserves_comments() -> None:
    text = "# keep me\nmcp_servers:\n  drop:\n    command: x\n  keep:\n    command: y\n"
    out = me.remove_entry(ConfigFileFormat.YAML, text, "drop")
    assert "# keep me" in out
    entries = me.parse_entries(ConfigFileFormat.YAML, out, source="config")
    assert {e.name for e in entries} == {"keep"}
    with pytest.raises(McpEntryNotFound):
        me.remove_entry(ConfigFileFormat.YAML, out, "nope")


def test_remove_entry_json_custom_container() -> None:
    text = '{"mcp": {"a": {"command": "x"}, "b": {"command": "y"}}}'
    out = me.remove_entry(ConfigFileFormat.JSON, text, "a", container_key="mcp")
    entries = me.parse_entries(ConfigFileFormat.JSON, out, source="config", container_key="mcp")
    assert {e.name for e in entries} == {"b"}

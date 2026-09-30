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
        "secret_refs": {"JIRA_API_TOKEN": "mcp/codex/jira/JIRA_API_TOKEN"},
    }


def test_to_transport_config_http() -> None:
    entries = me.parse_entries(ConfigFileFormat.TOML, CODEX_TOML, source="config")
    gas = next(e for e in entries if e.name == "gas")
    cfg = me.to_transport_config(gas, {"Authorization": "mcp/gas/Authorization"})
    assert cfg == {
        "type": "http",
        "url": "https://gas.example/mcp",
        "headers": {},
        "secret_refs": {"Authorization": "mcp/gas/Authorization"},
    }


def test_parse_tolerates_malformed_fields() -> None:
    text = '{"mcpServers": {"weird": {"command": "c", "env": "oops", "headers": 5, "args": "abc"}}}'
    [e] = me.parse_entries(ConfigFileFormat.JSON, text, source="global")
    assert e.env == {} and e.headers == {} and e.args == ()


def test_repr_hides_env_and_header_values() -> None:
    entries = me.parse_entries(ConfigFileFormat.JSON, CLAUDE_JSON, source="global")
    jira = next(e for e in entries if e.name == "jira")
    assert "tok123" not in repr(jira)


# --- new shapes: container_key, command-array, environment ---


def test_remove_entry_json_custom_container() -> None:
    text = '{"mcp": {"a": {"command": "x"}, "b": {"command": "y"}}}'
    out = me.remove_entry(ConfigFileFormat.JSON, text, "a", container_key="mcp")
    entries = me.parse_entries(ConfigFileFormat.JSON, out, source="config", container_key="mcp")
    assert {e.name for e in entries} == {"b"}


# --- nested JSON container (a dotted `mcp.servers` container key) --------------------

NESTED_JSON = (
    '{"gateway": {"port": 18789}, "mcp": {"servers": {'
    '"coffer": {"command": "/bin/coffer-mcp-shim"}, '
    '"files": {"command": "npx", "args": ["-y", "files-mcp"]}}}}'
)


def test_parse_entries_json_dotted_container():
    entries = me.parse_entries(
        ConfigFileFormat.JSON, NESTED_JSON, source="config", container_key="mcp.servers"
    )
    by_name = {e.name: e for e in entries}
    assert set(by_name) == {"coffer", "files"}
    assert by_name["coffer"].is_coffer is True
    assert by_name["files"].command == "npx"
    assert by_name["files"].args == ("-y", "files-mcp")


def test_parse_entries_json_dotted_container_absent_or_scalar_is_empty():
    assert (
        me.parse_entries(ConfigFileFormat.JSON, "{}", source="config", container_key="mcp.servers")
        == []
    )
    scalar = '{"mcp": "coffer"}'
    assert (
        me.parse_entries(
            ConfigFileFormat.JSON, scalar, source="config", container_key="mcp.servers"
        )
        == []
    )


def test_remove_entry_json_dotted_container():
    out = me.remove_entry(ConfigFileFormat.JSON, NESTED_JSON, "files", container_key="mcp.servers")
    entries = me.parse_entries(
        ConfigFileFormat.JSON, out, source="config", container_key="mcp.servers"
    )
    assert [e.name for e in entries] == ["coffer"]
    with pytest.raises(McpEntryNotFound):
        me.remove_entry(ConfigFileFormat.JSON, out, "files", container_key="mcp.servers")


# --- cwd / extra keys / masking (the one-entry detail read) -----------------

DETAIL_TOML = """
[mcp_servers.full]
command = "uvx"
args = ["srv"]
cwd = "/work"
startup_timeout_sec = 20
enabled = true
bearer_token = "tok"
empty_token = ""
[mcp_servers.full.env]
A = "1"
[mcp_servers.full.oauth]
client_secret = "s"
scopes = ["read"]
"""


def test_parse_keeps_cwd_and_every_other_key_as_plain_values() -> None:
    (entry,) = me.parse_entries(ConfigFileFormat.TOML, DETAIL_TOML, source="config")
    assert entry.cwd == "/work"
    # Typed fields (command/args/env/enabled/cwd) never repeat in extra, and
    # tomlkit items come out as plain Python.
    assert entry.extra == {
        "startup_timeout_sec": 20,
        "bearer_token": "tok",
        "empty_token": "",
        "oauth": {"client_secret": "s", "scopes": ["read"]},
    }
    assert type(entry.extra["oauth"]) is dict
    assert type(entry.extra["startup_timeout_sec"]) is int


def test_parse_json_entry_without_cwd_or_extra() -> None:
    entries = me.parse_entries(ConfigFileFormat.JSON, CLAUDE_JSON, source="global")
    jira = next(e for e in entries if e.name == "jira")
    assert jira.cwd is None
    assert jira.extra == {}


def test_extra_values_stay_out_of_repr() -> None:
    (entry,) = me.parse_entries(ConfigFileFormat.TOML, DETAIL_TOML, source="config")
    assert "bearer_token" not in repr(entry)
    assert "client_secret" not in repr(entry)


def test_masked_extra_withholds_secret_keys_and_tables_that_nest_them() -> None:
    fields = me.masked_extra(
        {
            "timeout": 20,
            "bearer_token": "tok",
            "empty_token": "",
            "oauth": {"client_secret": "s"},
            "hosts": [{"api_key": "k"}],
            "type": "sse",
            "flags": {"debug": True},
        }
    )
    assert [f.key for f in fields] == sorted(
        ["timeout", "bearer_token", "empty_token", "oauth", "hosts", "type", "flags"]
    )
    by_key = {f.key: f for f in fields}
    assert by_key["timeout"] == me.ExtraField("timeout", "20", False)
    assert by_key["type"] == me.ExtraField("type", "sse", False)
    assert by_key["flags"] == me.ExtraField("flags", '{"debug": true}', False)
    # An empty secret-looking value hides nothing, so it is shown as it is.
    assert by_key["empty_token"] == me.ExtraField("empty_token", "", False)
    for key in ("bearer_token", "oauth", "hosts"):
        assert by_key[key] == me.ExtraField(key, None, True)


def test_looks_secret_matches_the_adopt_pattern() -> None:
    assert me.looks_secret("GITHUB_TOKEN")
    assert me.looks_secret("x_api_key")
    assert me.looks_secret("Authorization")
    assert not me.looks_secret("LANG")


def test_matches_transport_compares_command_args_or_url() -> None:
    entries = {e.name: e for e in me.parse_entries(ConfigFileFormat.TOML, CODEX_TOML, source="c")}
    local, gas = entries["local"], entries["gas"]
    assert me.matches_transport(
        local, {"type": "stdio", "command": "npx", "args": ["-y", "some-mcp"]}
    )
    assert not me.matches_transport(local, {"type": "stdio", "command": "npx", "args": []})
    assert not me.matches_transport(local, {"type": "stdio", "command": "npx", "args": "bad"})
    assert me.matches_transport(gas, {"type": "http", "url": "https://gas.example/mcp"})
    assert not me.matches_transport(gas, {"type": "stdio", "url": "https://gas.example/mcp"})

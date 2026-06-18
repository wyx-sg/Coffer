"""Unit tests for the pure Coffer-MCP entry text transforms (JSON + TOML)."""

from __future__ import annotations

import json

import pytest
import tomlkit

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.mcp_injection import McpEntryStyle
from coffer.domain.agent.mcp_install import (
    COFFER_SERVER_KEY,
    apply_install,
    apply_uninstall,
    installed_command,
    is_installed,
)
from coffer.domain.errors import ConfigFileFormatInvalid

SHIM = "/usr/local/bin/coffer-mcp-shim"

# --- JSON (Claude Code ~/.claude.json) ---


def test_json_install_into_empty():
    out = apply_install(ConfigFileFormat.JSON, "", SHIM)
    data = json.loads(out)
    assert data["mcpServers"][COFFER_SERVER_KEY] == {"command": SHIM}
    assert is_installed(ConfigFileFormat.JSON, out)
    assert installed_command(ConfigFileFormat.JSON, out) == SHIM


def test_json_install_preserves_existing_keys_and_servers():
    existing = json.dumps({"oauthAccount": {"id": "x"}, "mcpServers": {"other": {"command": "y"}}})
    out = apply_install(ConfigFileFormat.JSON, existing, SHIM)
    data = json.loads(out)
    assert data["oauthAccount"] == {"id": "x"}
    assert data["mcpServers"]["other"] == {"command": "y"}
    assert data["mcpServers"][COFFER_SERVER_KEY] == {"command": SHIM}


def test_json_install_idempotent():
    once = apply_install(ConfigFileFormat.JSON, "", SHIM)
    twice = apply_install(ConfigFileFormat.JSON, once, SHIM)
    data = json.loads(twice)
    # Exactly one coffer entry, command updated in place.
    assert list(data["mcpServers"]).count(COFFER_SERVER_KEY) == 1


def test_json_uninstall_removes_only_coffer():
    installed = apply_install(
        ConfigFileFormat.JSON,
        json.dumps({"mcpServers": {"other": {"command": "y"}}}),
        SHIM,
    )
    out = apply_uninstall(ConfigFileFormat.JSON, installed)
    data = json.loads(out)
    assert COFFER_SERVER_KEY not in data["mcpServers"]
    assert data["mcpServers"]["other"] == {"command": "y"}
    assert not is_installed(ConfigFileFormat.JSON, out)


def test_json_status_false_for_empty_and_absent():
    assert is_installed(ConfigFileFormat.JSON, "") is False
    assert is_installed(ConfigFileFormat.JSON, "{}") is False
    assert installed_command(ConfigFileFormat.JSON, "{}") is None


def test_json_malformed_raises():
    with pytest.raises(ConfigFileFormatInvalid):
        apply_install(ConfigFileFormat.JSON, "{not json", SHIM)


# --- TOML (Codex config.toml) ---


def test_toml_install_into_empty():
    out = apply_install(ConfigFileFormat.TOML, "", SHIM)
    doc = tomlkit.parse(out)
    assert doc["mcp_servers"][COFFER_SERVER_KEY]["command"] == SHIM
    assert is_installed(ConfigFileFormat.TOML, out)
    assert installed_command(ConfigFileFormat.TOML, out) == SHIM


def test_toml_install_preserves_comments_and_other_tables():
    existing = '# my config\nmodel = "o1"\n\n[mcp_servers.other]\ncommand = "y"\n'
    out = apply_install(ConfigFileFormat.TOML, existing, SHIM)
    assert "# my config" in out
    assert 'model = "o1"' in out
    doc = tomlkit.parse(out)
    assert doc["mcp_servers"]["other"]["command"] == "y"
    assert doc["mcp_servers"][COFFER_SERVER_KEY]["command"] == SHIM


def test_toml_install_idempotent():
    once = apply_install(ConfigFileFormat.TOML, "", SHIM)
    twice = apply_install(ConfigFileFormat.TOML, once, SHIM)
    doc = tomlkit.parse(twice)
    assert is_installed(ConfigFileFormat.TOML, twice)
    # Only one coffer subtable.
    assert len([k for k in doc["mcp_servers"] if k == COFFER_SERVER_KEY]) == 1


def test_toml_uninstall_removes_only_coffer():
    installed = apply_install(ConfigFileFormat.TOML, '[mcp_servers.other]\ncommand = "y"\n', SHIM)
    out = apply_uninstall(ConfigFileFormat.TOML, installed)
    doc = tomlkit.parse(out)
    assert COFFER_SERVER_KEY not in doc.get("mcp_servers", {})
    assert doc["mcp_servers"]["other"]["command"] == "y"
    assert not is_installed(ConfigFileFormat.TOML, out)


def test_toml_status_false_for_empty():
    assert is_installed(ConfigFileFormat.TOML, "") is False
    assert is_installed(ConfigFileFormat.TOML, 'model = "o1"\n') is False


def test_toml_malformed_raises():
    with pytest.raises(ConfigFileFormatInvalid):
        apply_install(ConfigFileFormat.TOML, "a = = 1", SHIM)


def test_uninstall_absent_is_noop():
    # No coffer entry present -> uninstall leaves a parseable, coffer-free doc.
    out_json = apply_uninstall(ConfigFileFormat.JSON, "{}")
    assert not is_installed(ConfigFileFormat.JSON, out_json)
    out_toml = apply_uninstall(ConfigFileFormat.TOML, 'model = "o1"\n')
    assert not is_installed(ConfigFileFormat.TOML, out_toml)


# --- hand-edited / hostile configs must not crash (non-table mcp_servers) ---


def test_toml_install_recreates_non_table_mcp_servers():
    """A hand-edited `mcp_servers = "x"` scalar must not crash install."""
    out = apply_install(ConfigFileFormat.TOML, 'mcp_servers = "oops"\n', SHIM)
    doc = tomlkit.parse(out)
    assert doc["mcp_servers"][COFFER_SERVER_KEY]["command"] == SHIM
    assert is_installed(ConfigFileFormat.TOML, out)


def test_toml_status_false_for_scalar_mcp_servers():
    """A scalar `mcp_servers` containing the substring 'coffer' must not
    false-positive via `in`, and installed_command must not raise."""
    text = 'mcp_servers = "coffer-ish"\n'
    assert is_installed(ConfigFileFormat.TOML, text) is False
    assert installed_command(ConfigFileFormat.TOML, text) is None


def test_toml_installed_command_none_for_scalar_coffer_entry():
    """`coffer` mapped to a scalar (not a table) must not raise in
    installed_command — is_installed is True but there is no `.command`."""
    text = '[mcp_servers]\ncoffer = "x"\n'
    assert is_installed(ConfigFileFormat.TOML, text) is True
    assert installed_command(ConfigFileFormat.TOML, text) is None


def test_toml_uninstall_noop_for_scalar_mcp_servers():
    """Uninstall against a scalar `mcp_servers` must be a parseable no-op."""
    out = apply_uninstall(ConfigFileFormat.TOML, 'mcp_servers = "coffer-ish"\n')
    assert tomlkit.parse(out)["mcp_servers"] == "coffer-ish"


def test_json_install_preserves_non_ascii():
    """ensure_ascii=False keeps unicode in ~/.claude.json intact rather than
    rewriting it to \\uXXXX escapes."""
    existing = json.dumps({"project": "/Users/张三/code"}, ensure_ascii=False)
    out = apply_install(ConfigFileFormat.JSON, existing, SHIM)
    assert "/Users/张三/code" in out
    assert "\\u" not in out


# --- YAML (Hermes ~/.hermes/config.yaml, container `mcp_servers`) ---


def test_yaml_install_into_empty():
    out = apply_install(ConfigFileFormat.YAML, "", SHIM)
    import yaml

    data = yaml.safe_load(out)
    assert data["mcp_servers"][COFFER_SERVER_KEY] == {"command": SHIM}
    assert is_installed(ConfigFileFormat.YAML, out)
    assert installed_command(ConfigFileFormat.YAML, out) == SHIM


def test_yaml_install_preserves_comments_and_other_keys():
    existing = "# my hermes config\nmodel: gpt\n\nmcp_servers:\n  other:\n    command: y\n"
    out = apply_install(ConfigFileFormat.YAML, existing, SHIM)
    assert "# my hermes config" in out  # round-trip preserves comments
    import yaml

    data = yaml.safe_load(out)
    assert data["model"] == "gpt"
    assert data["mcp_servers"]["other"] == {"command": "y"}
    assert data["mcp_servers"][COFFER_SERVER_KEY]["command"] == SHIM


def test_yaml_install_idempotent_and_uninstall():
    once = apply_install(ConfigFileFormat.YAML, "", SHIM)
    twice = apply_install(ConfigFileFormat.YAML, once, SHIM)
    assert is_installed(ConfigFileFormat.YAML, twice)
    out = apply_uninstall(ConfigFileFormat.YAML, twice)
    assert not is_installed(ConfigFileFormat.YAML, out)


def test_yaml_status_false_for_empty():
    assert is_installed(ConfigFileFormat.YAML, "") is False
    assert is_installed(ConfigFileFormat.YAML, "model: gpt\n") is False


# --- shape axis: OpenCode JSON, container `mcp`, typed command-array ---


def test_json_mcp_container_typed_array_install():
    out = apply_install(
        ConfigFileFormat.JSON,
        "",
        SHIM,
        container_key="mcp",
        entry_style=McpEntryStyle.TYPED_COMMAND_ARRAY,
    )
    data = json.loads(out)
    assert data["mcp"][COFFER_SERVER_KEY] == {"type": "local", "command": [SHIM]}
    # status/command/uninstall all honour the same container_key + array shape
    assert is_installed(ConfigFileFormat.JSON, out, container_key="mcp")
    assert installed_command(ConfigFileFormat.JSON, out, container_key="mcp") == SHIM
    # default container (`mcpServers`) must NOT see it
    assert is_installed(ConfigFileFormat.JSON, out) is False
    gone = apply_uninstall(ConfigFileFormat.JSON, out, container_key="mcp")
    assert is_installed(ConfigFileFormat.JSON, gone, container_key="mcp") is False


def test_json_mcp_container_preserves_sibling_entries():
    existing = json.dumps({"mcp": {"other": {"type": "local", "command": ["y"]}}})
    out = apply_install(
        ConfigFileFormat.JSON,
        existing,
        SHIM,
        container_key="mcp",
        entry_style=McpEntryStyle.TYPED_COMMAND_ARRAY,
    )
    data = json.loads(out)
    assert data["mcp"]["other"] == {"type": "local", "command": ["y"]}
    assert data["mcp"][COFFER_SERVER_KEY]["command"] == [SHIM]


# --- ADR-026: install embeds the agent identity as `--agent <name>` ---


@pytest.mark.acceptance(spec="004-agent-registry", scenario="install embeds the agent identity")
def test_json_command_map_install_embeds_agent_arg():
    """COMMAND_MAP (Claude Code / Cursor): a separate `args` list carries
    `--agent <name>` while `command` stays the bare shim path."""
    out = apply_install(ConfigFileFormat.JSON, "", SHIM, agent_name="claude_code")
    entry = json.loads(out)["mcpServers"][COFFER_SERVER_KEY]
    assert entry == {"command": SHIM, "args": ["--agent", "claude_code"]}
    # Round-trip: the installed shim path is still resolvable.
    assert installed_command(ConfigFileFormat.JSON, out) == SHIM


def test_json_typed_command_array_install_embeds_agent_arg():
    """TYPED_COMMAND_ARRAY (OpenCode): `--agent <name>` is appended to the
    command array after the shim path."""
    out = apply_install(
        ConfigFileFormat.JSON,
        "",
        SHIM,
        container_key="mcp",
        entry_style=McpEntryStyle.TYPED_COMMAND_ARRAY,
        agent_name="claude_code",
    )
    entry = json.loads(out)["mcp"][COFFER_SERVER_KEY]
    assert entry == {"type": "local", "command": [SHIM, "--agent", "claude_code"]}
    assert installed_command(ConfigFileFormat.JSON, out, container_key="mcp") == SHIM


def test_toml_install_embeds_agent_arg():
    out = apply_install(ConfigFileFormat.TOML, "", SHIM, agent_name="codex")
    doc = tomlkit.parse(out)
    assert doc["mcp_servers"][COFFER_SERVER_KEY]["command"] == SHIM
    assert list(doc["mcp_servers"][COFFER_SERVER_KEY]["args"]) == ["--agent", "codex"]
    assert installed_command(ConfigFileFormat.TOML, out) == SHIM


def test_install_without_agent_name_omits_arg_backward_compat():
    """agent_name=None (the default) must reproduce the original entry shape —
    no `args` key — so existing callers and configs are unchanged."""
    json_out = apply_install(ConfigFileFormat.JSON, "", SHIM)
    assert json.loads(json_out)["mcpServers"][COFFER_SERVER_KEY] == {"command": SHIM}

    array_out = apply_install(
        ConfigFileFormat.JSON,
        "",
        SHIM,
        container_key="mcp",
        entry_style=McpEntryStyle.TYPED_COMMAND_ARRAY,
    )
    assert json.loads(array_out)["mcp"][COFFER_SERVER_KEY] == {
        "type": "local",
        "command": [SHIM],
    }

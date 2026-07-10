"""Unit tests for the pure Coffer-MCP entry text transforms (JSON + TOML)."""

from __future__ import annotations

import json

import pytest
import tomlkit

from coffer.domain.agent.config_files import ConfigFileFormat
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


# --- self-reported agent identity (spec 004 FR-019 amended, Task 9) -------------


def test_entry_fields_command_map_with_agent_name():
    from coffer.domain.agent.mcp_injection import McpEntryStyle
    from coffer.domain.agent.mcp_install import _entry_fields

    assert _entry_fields(SHIM, McpEntryStyle.COMMAND_MAP, "my_agent") == {
        "command": SHIM,
        "args": ["--agent", "my_agent"],
    }


def test_entry_fields_command_map_without_agent_name():
    from coffer.domain.agent.mcp_injection import McpEntryStyle
    from coffer.domain.agent.mcp_install import _entry_fields

    assert _entry_fields(SHIM, McpEntryStyle.COMMAND_MAP, None) == {"command": SHIM}
    # agent_name defaults to None when omitted entirely.
    assert _entry_fields(SHIM, McpEntryStyle.COMMAND_MAP) == {"command": SHIM}


def test_entry_fields_typed_local_object_with_agent_name():
    from coffer.domain.agent.mcp_injection import McpEntryStyle
    from coffer.domain.agent.mcp_install import _entry_fields

    assert _entry_fields(SHIM, McpEntryStyle.TYPED_LOCAL_OBJECT, "my_agent") == {
        "type": "local",
        "command": [SHIM, "--agent", "my_agent"],
        "enabled": True,
    }


def test_entry_fields_typed_command_array_with_agent_name():
    from coffer.domain.agent.mcp_injection import McpEntryStyle
    from coffer.domain.agent.mcp_install import _entry_fields

    assert _entry_fields(SHIM, McpEntryStyle.TYPED_COMMAND_ARRAY, "my_agent") == {
        "type": "local",
        "command": [SHIM, "--agent", "my_agent"],
    }


def test_json_command_map_entry_with_agent_name_carries_args():
    out = apply_install(ConfigFileFormat.JSON, "", SHIM, agent_name="my_agent")
    data = json.loads(out)
    assert data["mcpServers"][COFFER_SERVER_KEY] == {
        "command": SHIM,
        "args": ["--agent", "my_agent"],
    }
    assert is_installed(ConfigFileFormat.JSON, out)
    assert installed_command(ConfigFileFormat.JSON, out) == SHIM


def test_json_command_map_entry_without_agent_name_has_no_args_key():
    """Backward compatible default: no agent_name ⇒ the pre-Task-9 shape,
    unaffected by the new parameter."""
    out = apply_install(ConfigFileFormat.JSON, "", SHIM)
    data = json.loads(out)
    assert data["mcpServers"][COFFER_SERVER_KEY] == {"command": SHIM}
    assert "args" not in data["mcpServers"][COFFER_SERVER_KEY]


def test_toml_command_map_entry_with_agent_name_carries_args():
    out = apply_install(ConfigFileFormat.TOML, "", SHIM, agent_name="codex")
    doc = tomlkit.parse(out)
    entry = doc["mcp_servers"][COFFER_SERVER_KEY]
    assert entry["command"] == SHIM
    assert list(entry["args"]) == ["--agent", "codex"]
    assert is_installed(ConfigFileFormat.TOML, out)
    assert installed_command(ConfigFileFormat.TOML, out) == SHIM


def test_json_typed_local_object_entry_with_agent_name_appends_to_command_array():
    """Typed-array styles have no ``args`` key — the agent flag is appended
    directly onto the ``command`` array (spec 004 FR-019 amended)."""
    from coffer.domain.agent.mcp_injection import McpEntryStyle

    out = apply_install(
        ConfigFileFormat.JSON,
        "",
        SHIM,
        container_key="mcp",
        entry_style=McpEntryStyle.TYPED_LOCAL_OBJECT,
        agent_name="opencode_agent",
    )
    data = json.loads(out)
    assert data["mcp"][COFFER_SERVER_KEY] == {
        "type": "local",
        "command": [SHIM, "--agent", "opencode_agent"],
        "enabled": True,
    }
    assert is_installed(ConfigFileFormat.JSON, out, container_key="mcp")
    assert installed_command(ConfigFileFormat.JSON, out, container_key="mcp") == SHIM


def test_typed_command_array_entry_with_agent_name_appends_to_command_array():
    from coffer.domain.agent.mcp_injection import McpEntryStyle

    out = apply_install(
        ConfigFileFormat.JSON,
        "",
        SHIM,
        container_key="mcp",
        entry_style=McpEntryStyle.TYPED_COMMAND_ARRAY,
        agent_name="my_agent",
    )
    data = json.loads(out)
    assert data["mcp"][COFFER_SERVER_KEY] == {
        "type": "local",
        "command": [SHIM, "--agent", "my_agent"],
    }
    assert is_installed(ConfigFileFormat.JSON, out, container_key="mcp")
    assert installed_command(ConfigFileFormat.JSON, out, container_key="mcp") == SHIM


def test_json_install_with_agent_name_is_idempotent_on_reinstall():
    """Re-install (the migration path for pre-Task-9 entries, see module
    docstring) replaces the entry in place — never duplicates it."""
    once = apply_install(ConfigFileFormat.JSON, "", SHIM, agent_name="my_agent")
    twice = apply_install(ConfigFileFormat.JSON, once, SHIM, agent_name="my_agent")
    data = json.loads(twice)
    assert list(data["mcpServers"]).count(COFFER_SERVER_KEY) == 1
    assert data["mcpServers"][COFFER_SERVER_KEY]["args"] == ["--agent", "my_agent"]


def test_json_preexisting_entry_without_args_is_detected_as_installed():
    """Regression: agents installed BEFORE this change wrote entries with no
    ``args`` key at all. is_installed/installed_command must still report
    them as installed (they key on COFFER_SERVER_KEY, not on ``args``) —
    re-install (not auto-migration) is the upgrade path to add the flag."""
    pre_existing = json.dumps({"mcpServers": {COFFER_SERVER_KEY: {"command": SHIM}}})
    assert is_installed(ConfigFileFormat.JSON, pre_existing)
    assert installed_command(ConfigFileFormat.JSON, pre_existing) == SHIM

    # Re-install (the migration path) rewrites it with the agent flag, in place.
    upgraded = apply_install(ConfigFileFormat.JSON, pre_existing, SHIM, agent_name="my_agent")
    data = json.loads(upgraded)
    assert list(data["mcpServers"]).count(COFFER_SERVER_KEY) == 1
    assert data["mcpServers"][COFFER_SERVER_KEY] == {
        "command": SHIM,
        "args": ["--agent", "my_agent"],
    }


def test_json_entry_with_args_is_detected_as_installed_and_uninstall_removes_it():
    """Regression: an entry that already carries ``args`` (post-Task-9 shape)
    is still detected as installed, and uninstall still removes exactly it —
    `_coffer_command`/`is_installed` key on `COFFER_SERVER_KEY`, unaffected by
    the presence of an `args` list."""
    installed = apply_install(ConfigFileFormat.JSON, "", SHIM, agent_name="my_agent")
    assert is_installed(ConfigFileFormat.JSON, installed)
    assert installed_command(ConfigFileFormat.JSON, installed) == SHIM

    back = apply_uninstall(ConfigFileFormat.JSON, installed)
    assert not is_installed(ConfigFileFormat.JSON, back)


def test_json_install_preserves_non_ascii():
    """ensure_ascii=False keeps unicode in ~/.claude.json intact rather than
    rewriting it to \\uXXXX escapes."""
    existing = json.dumps({"project": "/Users/张三/code"}, ensure_ascii=False)
    out = apply_install(ConfigFileFormat.JSON, existing, SHIM)
    assert "/Users/张三/code" in out
    assert "\\u" not in out


# --- opencode typed-local-object entry style (ADR-040) ---


def test_json_typed_local_object_entry_install_detect_uninstall():
    from coffer.domain.agent.mcp_injection import McpEntryStyle

    out = apply_install(
        ConfigFileFormat.JSON,
        "",
        SHIM,
        container_key="mcp",
        entry_style=McpEntryStyle.TYPED_LOCAL_OBJECT,
    )
    data = json.loads(out)
    assert data["mcp"][COFFER_SERVER_KEY] == {
        "type": "local",
        "command": [SHIM],
        "enabled": True,
    }
    # Detection / command extraction / uninstall are style-agnostic — they key off
    # the container + coffer key and handle the command-array shape.
    assert is_installed(ConfigFileFormat.JSON, out, container_key="mcp")
    assert installed_command(ConfigFileFormat.JSON, out, container_key="mcp") == SHIM
    back = apply_uninstall(ConfigFileFormat.JSON, out, container_key="mcp")
    assert not is_installed(ConfigFileFormat.JSON, back, container_key="mcp")


def test_json_typed_local_object_preserves_user_mcp_entries():
    from coffer.domain.agent.mcp_injection import McpEntryStyle

    existing = json.dumps({"mcp": {"other": {"type": "local", "command": ["y"]}}})
    out = apply_install(
        ConfigFileFormat.JSON,
        existing,
        SHIM,
        container_key="mcp",
        entry_style=McpEntryStyle.TYPED_LOCAL_OBJECT,
    )
    data = json.loads(out)
    assert data["mcp"]["other"] == {"type": "local", "command": ["y"]}  # user entry kept
    assert data["mcp"][COFFER_SERVER_KEY]["enabled"] is True


# --- nested JSON container (openclaw `mcp.servers`, ADR-044) --------------------


def test_json_dotted_container_install_into_empty():
    out = apply_install(ConfigFileFormat.JSON, "", SHIM, container_key="mcp.servers")
    data = json.loads(out)
    assert data["mcp"]["servers"][COFFER_SERVER_KEY] == {"command": SHIM}
    assert is_installed(ConfigFileFormat.JSON, out, container_key="mcp.servers")
    assert installed_command(ConfigFileFormat.JSON, out, container_key="mcp.servers") == SHIM


def test_json_dotted_container_preserves_siblings_at_every_level():
    existing = json.dumps(
        {
            "gateway": {"port": 18789},
            "mcp": {"bridge": True, "servers": {"other": {"command": "y"}}},
        }
    )
    out = apply_install(ConfigFileFormat.JSON, existing, SHIM, container_key="mcp.servers")
    data = json.loads(out)
    assert data["gateway"] == {"port": 18789}  # unrelated top-level key kept
    assert data["mcp"]["bridge"] is True  # sibling inside the dotted path kept
    assert data["mcp"]["servers"]["other"] == {"command": "y"}  # user server kept
    assert data["mcp"]["servers"][COFFER_SERVER_KEY] == {"command": SHIM}


def test_json_dotted_container_uninstall_removes_only_coffer():
    existing = json.dumps({"mcp": {"servers": {"other": {"command": "y"}}}})
    out = apply_install(ConfigFileFormat.JSON, existing, SHIM, container_key="mcp.servers")
    back = apply_uninstall(ConfigFileFormat.JSON, out, container_key="mcp.servers")
    data = json.loads(back)
    assert data["mcp"]["servers"]["other"] == {"command": "y"}
    assert COFFER_SERVER_KEY not in data["mcp"]["servers"]
    assert not is_installed(ConfigFileFormat.JSON, back, container_key="mcp.servers")


def test_json_dotted_container_status_false_when_path_absent_or_scalar():
    assert not is_installed(ConfigFileFormat.JSON, "{}", container_key="mcp.servers")
    # A hand-edit that left a scalar at a step never false-positives (or raises).
    scalar = json.dumps({"mcp": "coffer"})
    assert not is_installed(ConfigFileFormat.JSON, scalar, container_key="mcp.servers")
    assert installed_command(ConfigFileFormat.JSON, scalar, container_key="mcp.servers") is None


def test_json_dotted_container_install_replaces_scalar_step():
    # Mirrors the flat branch's isinstance(dict) guard: a scalar at a step is
    # replaced so the install always lands.
    out = apply_install(
        ConfigFileFormat.JSON, json.dumps({"mcp": 42}), SHIM, container_key="mcp.servers"
    )
    assert json.loads(out)["mcp"]["servers"][COFFER_SERVER_KEY] == {"command": SHIM}

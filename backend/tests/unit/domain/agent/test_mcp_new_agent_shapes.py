"""Coffer's MCP entry in the OpenCode command-array shape and the DeepSeek
Harness Cordis patch (spec agent-registry/opencode and
agent-registry/deepseek-harness "Install Coffer's MCP entry")."""

from __future__ import annotations

import json

import pytest

from coffer.domain.agent import mcp_cordis
from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.mcp_entries import parse_entries, remove_entry
from coffer.domain.agent.mcp_injection import McpEntryStyle
from coffer.domain.agent.mcp_install import (
    apply_install,
    apply_uninstall,
    desired_entry,
    installed_agent_uid,
    installed_entry,
    is_installed,
)
from coffer.domain.errors import ConfigFileFormatInvalid
from coffer.domain.workspace_errors import McpEntryNotEditable

SHIM = "/Applications/Coffer.app/Contents/MacOS/coffer-mcp-shim"
JSON = ConfigFileFormat.JSON
YAML = ConfigFileFormat.YAML


# --- OpenCode -----------------------------------------------------------------


def _opencode_install(text: str) -> str:
    return apply_install(
        JSON,
        text,
        SHIM,
        container_key="mcp",
        entry_style=McpEntryStyle.COMMAND_ARRAY,
        agent_uid="u1",
    )


def test_opencode_entry_is_a_typed_command_array() -> None:
    out = json.loads(_opencode_install('{"model": "anthropic/x"}'))
    assert out["model"] == "anthropic/x"
    assert out["mcp"]["coffer"] == {"type": "local", "command": [SHIM, "--agent-uid", "u1"]}


def test_opencode_entry_reads_back_like_a_command_map() -> None:
    text = _opencode_install("")
    assert is_installed(JSON, text, container_key="mcp")
    assert installed_entry(JSON, text, container_key="mcp") == desired_entry(SHIM, "u1")
    assert installed_agent_uid(JSON, text, container_key="mcp") == "u1"


def test_opencode_lists_both_v1_and_v2_servers() -> None:
    text = json.dumps(
        {
            "mcp": {
                "old": {"type": "local", "command": ["npx", "old"], "enabled": False},
                "servers": {"new": {"type": "remote", "url": "https://x/mcp"}},
            }
        }
    )
    entries = {e.name: e for e in parse_entries(JSON, text, source="config", container_key="mcp")}
    assert set(entries) == {"old", "new"}
    assert entries["old"].command == "npx" and entries["old"].args == ("old",)
    assert entries["old"].enabled is False
    assert entries["new"].transport == "http"


def test_opencode_removes_a_v2_server() -> None:
    text = json.dumps({"mcp": {"servers": {"new": {"type": "local", "command": ["a"]}}}})
    after = json.loads(remove_entry(JSON, text, "new", container_key="mcp"))
    assert after == {"mcp": {"servers": {}}}


# --- DeepSeek Harness -----------------------------------------------------------

USER_PATCH = """\
# my own rows
- id: llm-deepseek
  config:
    reasoningEffort: max

- insert:
    - id: memory
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: memory
        transport: stdio
        command: memorix
        args: [serve]
        cwd: !!js process.cwd()
"""


def _dsh_install(text: str, uid: str = "u1") -> str:
    return apply_install(
        YAML, text, SHIM, entry_style=McpEntryStyle.CORDIS_ROW, agent_uid=uid
    )


def test_dsh_install_appends_a_managed_block_and_keeps_the_rest() -> None:
    out = _dsh_install(USER_PATCH)
    assert out.startswith(USER_PATCH.rstrip("\n"))
    assert mcp_cordis.BLOCK_START in out
    row = mcp_cordis.coffer_row(out)
    assert row is not None
    assert row["config"]["command"] == SHIM
    assert row["config"]["args"] == ["--agent-uid", "u1"]


def test_dsh_install_is_idempotent_and_replaces_its_block() -> None:
    once = _dsh_install(USER_PATCH)
    again = _dsh_install(once, uid="u2")
    assert again.count(mcp_cordis.BLOCK_START) == 1
    assert installed_agent_uid(YAML, again) == "u2"
    assert installed_entry(YAML, again) == desired_entry(SHIM, "u2")


def test_dsh_uninstall_restores_the_person_s_file() -> None:
    assert apply_uninstall(YAML, _dsh_install(USER_PATCH)).rstrip() == USER_PATCH.rstrip()
    assert not is_installed(YAML, USER_PATCH)


def test_dsh_install_into_an_empty_or_flow_empty_file() -> None:
    for start in ("", "[]\n", "# nothing yet\n"):
        out = _dsh_install(start)
        assert mcp_cordis.coffer_row(out) is not None


def test_dsh_refuses_a_document_it_cannot_append_to() -> None:
    with pytest.raises(ConfigFileFormatInvalid):
        _dsh_install("[{id: x}]\n")


def test_dsh_lists_rows_and_keeps_them_read_only() -> None:
    text = _dsh_install(USER_PATCH)
    entries = {e.name: e for e in parse_entries(YAML, text, source="patch")}
    assert set(entries) == {"memory", "coffer"}
    assert entries["memory"].command == "memorix"
    assert entries["memory"].args == ("serve",)
    assert entries["coffer"].is_coffer
    with pytest.raises(McpEntryNotEditable):
        remove_entry(YAML, text, "memory")

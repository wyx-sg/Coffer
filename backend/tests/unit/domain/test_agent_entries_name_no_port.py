"""Coffer's entries in an agent's config name no daemon port.

revise-web-ui-ia: daemon "after a restart on a new port every agent reconnects"
— the acceptance marker is added when the change is archived. A daemon that
restarts on a new port needs no rewrite of any agent's configuration, because
the MCP entry runs the shim and the delivery hook runs ``coffer memory hook``;
both find the daemon through ``daemon.json`` when they run.
"""

from __future__ import annotations

import json

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.mcp_install import apply_install
from coffer.domain.memory.delivery import hook_command


def test_the_mcp_entry_names_the_shim_and_no_port() -> None:
    fmt = ConfigFileFormat.JSON
    text = apply_install(fmt, "{}", "/Users/u/.coffer/bin/coffer-mcp-shim", agent_uid="a-1")
    entry = json.loads(text)["mcpServers"]["coffer"]
    assert entry["command"].endswith("coffer-mcp-shim")
    rendered = json.dumps(entry)
    for port in ("8000", "8123", "127.0.0.1", "localhost"):
        assert port not in rendered


def test_the_delivery_hook_names_no_port() -> None:
    command = hook_command("a-1", cli="/Users/u/.coffer/bin/coffer")
    for port in ("8000", "8123", "127.0.0.1", "localhost", "--port"):
        assert port not in command

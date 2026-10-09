"""Coffer's entries in an agent's config name no daemon port.

The restart itself is covered in
``tests/integration/infrastructure/daemon/test_fixed_port.py``. A daemon that
restarts on a new port needs no rewrite of any agent's configuration, because
the MCP entry runs the shim, which finds the daemon through ``daemon.json``
when it runs.
"""

from __future__ import annotations

import json

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.mcp_install import apply_install


def test_the_mcp_entry_names_the_shim_and_no_port() -> None:
    fmt = ConfigFileFormat.JSON
    text = apply_install(fmt, "{}", "/Users/u/.coffer/bin/coffer-mcp-shim", agent_uid="a-1")
    entry = json.loads(text)["mcpServers"]["coffer"]
    assert entry["command"].endswith("coffer-mcp-shim")
    rendered = json.dumps(entry)
    for port in ("38470", "8123", "127.0.0.1", "localhost"):
        assert port not in rendered

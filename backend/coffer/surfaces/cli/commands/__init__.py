"""Management commands, one module per page (spec resource-framework "Offer
every management operation on the command line")."""

from __future__ import annotations

import importlib

#: Every command module, imported once by ``main`` after the groups exist.
MODULES = (
    "custom_tool_groups",
    "custom_tool_tools",
    "custom_tool_envs",
    "approvals",
    "desktop_ops",
    "resources",
    "agents",
    "providers",
    "mcp_servers",
    "channels",
    "clis",
    "skills",
    "knowledge",
    "memory",
    "secrets_mgmt",
    "settings",
    "daemon_mgmt",
    "activity",
    "vault",
    "sync",
    "recorded",
)


def load() -> None:
    for name in MODULES:
        importlib.import_module(f"{__name__}.{name}")

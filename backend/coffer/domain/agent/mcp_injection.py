"""How Coffer's ``coffer`` MCP entry is written into an agent's config.

Two orthogonal axes describe MCP configuration across agents:

- **format** — the file's serialization (``json`` / ``toml`` / ``yaml``), which
  selects the parser/serializer (and comment-preservation strategy).
- **shape** — *where* the entries live (the ``container_key`` top-level table)
  and *how* a single entry is rendered (``entry_style``).

The two are independent: Claude Code and Cursor are both JSON ``mcpServers``
command-maps; OpenCode is JSON but its container is ``mcp`` with a typed
command-array entry; Hermes is YAML with an ``mcp_servers`` command-map. Bundling
them into one :class:`McpInjectionSpec` lets a single code path serve every
agent — the agent descriptor (spec 004) carries one spec per agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from coffer.domain.agent.config_files import ConfigFileFormat


class McpEntryStyle(StrEnum):
    """How a single stdio MCP server entry is rendered."""

    #: ``{"command": <shim>, "args": [...]}`` — Claude Code, Cursor, Codex, Hermes.
    COMMAND_MAP = "command_map"
    #: ``{"type": "local", "command": [<shim>, ...]}`` — OpenCode, where the
    #: executable is the first element of a ``command`` array and the entry is
    #: tagged with a transport ``type``.
    TYPED_COMMAND_ARRAY = "typed_command_array"


#: Default top-level container key per format, reproducing the pre-orthogonal
#: behaviour (Claude Code JSON ``mcpServers``; Codex TOML ``mcp_servers``). YAML
#: agents (Hermes) also use ``mcp_servers``. Agents that diverge (OpenCode/
#: OpenClaw ``mcp``) pass an explicit ``container_key``.
_DEFAULT_CONTAINER_KEY: dict[ConfigFileFormat, str] = {
    ConfigFileFormat.JSON: "mcpServers",
    ConfigFileFormat.TOML: "mcp_servers",
    ConfigFileFormat.YAML: "mcp_servers",
}


def default_container_key(fmt: ConfigFileFormat) -> str:
    """The conventional MCP container key for ``fmt``."""
    try:
        return _DEFAULT_CONTAINER_KEY[fmt]
    except KeyError:  # pragma: no cover - defensive
        raise AssertionError(f"no default MCP container key for format {fmt!r}") from None


@dataclass(frozen=True)
class McpInjectionSpec:
    """Where and how Coffer installs its ``coffer`` MCP entry for one agent.

    ``config_key`` names the allowlisted config file that holds the MCP servers
    (resolved against the agent's config dir by the application layer).
    """

    config_key: str
    container_key: str
    format: ConfigFileFormat
    entry_style: McpEntryStyle = McpEntryStyle.COMMAND_MAP

"""How Coffer's ``coffer`` MCP entry is written into an agent's config.

Two orthogonal axes describe MCP configuration across agents:

- **format** — the file's serialization (``json`` / ``toml`` / ``yaml``), which
  selects the parser/serializer (and comment-preservation strategy).
- **shape** — *where* the entries live (the ``container_key`` top-level table)
  and *how* a single entry is rendered (``entry_style``).

The two are independent: Claude Code uses JSON ``mcpServers`` command-maps;
Codex uses TOML ``mcp_servers`` command-maps. Bundling them into one
:class:`McpInjectionSpec` lets a single code path serve every agent — the agent
descriptor (spec 004) carries one spec per agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from coffer.domain.agent.config_files import ConfigFileFormat


class McpEntryStyle(StrEnum):
    """How a single stdio MCP server entry is rendered."""

    #: ``{"command": <shim>, "args": [...]}`` — used by Claude Code and Codex.
    COMMAND_MAP = "command_map"
    #: ``{"type": "local", "command": [<shim>, ...]}`` — the executable is the
    #: first element of a ``command`` array and the entry is tagged with a
    #: transport ``type``. Recognized extension point reserved for a future agent
    #: type; no current agent type uses it.
    TYPED_COMMAND_ARRAY = "typed_command_array"
    #: ``{"type": "local", "command": [<shim>, ...], "enabled": true}`` — opencode's
    #: shape: a typed-command array that also carries an explicit ``enabled`` flag
    #: (opencode's ``mcp`` block treats each server object as enabled only when the
    #: flag is present-and-true, so Coffer writes it).
    TYPED_LOCAL_OBJECT = "typed_local_object"


#: Default top-level container key per format, reproducing the pre-orthogonal
#: behaviour (Claude Code JSON ``mcpServers``; Codex TOML ``mcp_servers``). The
#: YAML slot also defaults to ``mcp_servers`` as a reserved extension point.
#: Agents that diverge from the default pass an explicit ``container_key``.
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
    A JSON ``container_key`` may be a dotted PATH (``mcp.servers`` — openclaw
    nests its servers map one level down); each dot descends one object.
    """

    config_key: str
    container_key: str
    format: ConfigFileFormat
    entry_style: McpEntryStyle = McpEntryStyle.COMMAND_MAP

"""Build / detect / remove Coffer's MCP-server entry in an agent's MCP config.

Pure domain text transforms — no filesystem access. The application layer reads
the agent's MCP config file, calls one of these to produce new text, and writes
it back through the atomic store.

The write is driven by two orthogonal axes (see :mod:`mcp_injection`):

- **format** — ``json`` / ``toml`` selects the parser/serializer (each
  preserving the user's other content: comments, ordering, unrelated keys).
- **shape** — ``container_key`` (the top-level table: ``mcpServers`` /
  ``mcp_servers``; a dotted JSON key like ``mcp.servers`` descends
  one object per dot) and ``entry_style`` (how a single stdio entry is
  rendered — today only the ``{"command": shim}`` command-map).

Defaults match both shipped agents — JSON ``mcpServers`` command-map
(Claude Code), TOML ``mcp_servers`` command-map (Codex); agents with
non-default shapes pass ``container_key`` / ``entry_style``.

Both wire Coffer via the stdio shim: ``command = <abs path to coffer-mcp-shim>``.
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any

import tomlkit

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.mcp_entries import (
    COFFER_SERVER_KEY,
    _json_container,
    _parse_json,
    _parse_toml,
)
from coffer.domain.agent.mcp_injection import McpEntryStyle, default_container_key


def _json_container_create(data: dict[str, Any], dotted_key: str) -> dict[str, Any]:
    """The JSON servers container for a possibly-dotted ``container_key``
    (``mcp.servers`` — an agent may nest its map one level down), creating each
    missing step. A hand-edit that left a non-object at any step is replaced
    (mirrors the flat branch's ``isinstance(dict)`` guard). JSON only — the
    TOML container keys in use carry no dots."""
    node = data
    for part in dotted_key.split("."):
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    return node


def _entry_fields(
    shim_path: str, entry_style: McpEntryStyle, agent_name: str | None = None
) -> dict[str, Any]:
    """The key/value pairs of a single stdio ``coffer`` entry for the style.

    ``agent_name``, when given, threads the installing agent's own name
    through as ``--agent <name>`` (spec agent-registry FR-015, amended) so the
    shim can self-report its identity at the MCP handshake. The command-map
    style carries it as a separate ``args`` list, mirroring how Claude Code /
    Codex already render stdio server args. ``agent_name=None`` (the default)
    omits the flag, for any caller that doesn't know the name.
    """
    fields: dict[str, Any] = {"command": shim_path}
    if agent_name:
        fields["args"] = ["--agent", agent_name]
    return fields


def _coffer_command(entry: Any) -> str | None:
    """Extract the shim path from an installed entry.

    Handles both ``command: "<shim>"`` (what Coffer writes) and
    ``command: ["<shim>", ...]`` (as a hand-edited config may spell it); returns
    ``None`` when the entry is not a mapping or carries no command.
    """
    if not isinstance(entry, MutableMapping):
        return None
    cmd = entry.get("command")
    if isinstance(cmd, (list, tuple)):
        return str(cmd[0]) if cmd else None
    return str(cmd) if cmd is not None else None


def apply_install(
    fmt: ConfigFileFormat,
    text: str,
    shim_path: str,
    *,
    container_key: str | None = None,
    entry_style: McpEntryStyle = McpEntryStyle.COMMAND_MAP,
    agent_name: str | None = None,
) -> str:
    """Return new config text with the ``coffer`` stdio entry inserted/updated.

    Idempotent: an existing ``coffer`` entry is replaced in place, never
    duplicated — including an entry written before ``agent_name`` support was
    added, which carries no ``--agent`` flag at all; re-installing rewrites it
    with the flag, in place, so there is no separate auto-migration path.
    """
    ck = container_key or default_container_key(fmt)
    fields = _entry_fields(shim_path, entry_style, agent_name)

    if fmt is ConfigFileFormat.JSON:
        data = _parse_json(text)
        servers = _json_container_create(data, ck)
        servers[COFFER_SERVER_KEY] = dict(fields)
        # ensure_ascii=False: ~/.claude.json holds the user's whole machine
        # state (project paths, history) which may be non-ASCII; escaping it to
        # \uXXXX on every install needlessly rewrites unrelated content.
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    if fmt is ConfigFileFormat.TOML:
        doc = _parse_toml(text)
        # Recreate `mcp_servers` if absent OR if a hand-edit left a non-table
        # value there — indexing into a scalar/array would raise (mirrors the
        # isinstance(dict) guard the JSON branch uses).
        if not isinstance(doc.get(ck), MutableMapping):
            doc[ck] = tomlkit.table(is_super_table=True)
        server = tomlkit.table()
        for key, value in fields.items():
            server[key] = value
        doc[ck][COFFER_SERVER_KEY] = server
        return tomlkit.dumps(doc)

    raise AssertionError(f"MCP install unsupported for format {fmt!r}")  # pragma: no cover


def apply_uninstall(fmt: ConfigFileFormat, text: str, *, container_key: str | None = None) -> str:
    """Return new config text with the ``coffer`` entry removed (no-op if absent)."""
    ck = container_key or default_container_key(fmt)

    if fmt is ConfigFileFormat.JSON:
        data = _parse_json(text)
        servers = _json_container(data, ck)
        if isinstance(servers, MutableMapping):
            servers.pop(COFFER_SERVER_KEY, None)
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    if fmt is ConfigFileFormat.TOML:
        doc = _parse_toml(text)
        servers = doc.get(ck)
        # isinstance guard: a scalar `mcp_servers` would make `KEY in servers` a
        # substring test and `del servers[KEY]` raise — treat non-tables as "no
        # coffer entry to remove".
        if isinstance(servers, MutableMapping) and COFFER_SERVER_KEY in servers:
            del servers[COFFER_SERVER_KEY]
        return tomlkit.dumps(doc)

    raise AssertionError(f"MCP uninstall unsupported for format {fmt!r}")  # pragma: no cover


def is_installed(fmt: ConfigFileFormat, text: str, *, container_key: str | None = None) -> bool:
    """Whether a ``coffer`` MCP-server entry is present in the config text."""
    if not text.strip():
        return False
    ck = container_key or default_container_key(fmt)
    if fmt is ConfigFileFormat.JSON:
        servers = _json_container(_parse_json(text), ck)
        return isinstance(servers, MutableMapping) and COFFER_SERVER_KEY in servers
    if fmt is ConfigFileFormat.TOML:
        servers = _parse_toml(text).get(ck)
        # isinstance guard so a scalar `mcp_servers` containing the substring
        # "coffer" can't false-positive via `in`.
        return isinstance(servers, MutableMapping) and COFFER_SERVER_KEY in servers
    raise AssertionError(f"MCP status unsupported for format {fmt!r}")  # pragma: no cover


def installed_command(
    fmt: ConfigFileFormat, text: str, *, container_key: str | None = None
) -> str | None:
    """The shim path of the installed coffer entry, or ``None`` if absent."""
    ck = container_key or default_container_key(fmt)
    if not is_installed(fmt, text, container_key=ck):
        return None
    if fmt is ConfigFileFormat.JSON:
        return _coffer_command(_json_container(_parse_json(text), ck)[COFFER_SERVER_KEY])
    return _coffer_command(_parse_toml(text)[ck][COFFER_SERVER_KEY])

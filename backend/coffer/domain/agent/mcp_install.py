"""Build / detect / remove Coffer's MCP-server entry in an agent's MCP config.

Pure domain text transforms — no filesystem access. The application layer reads
the agent's MCP config file, calls one of these to produce new text, and writes
it back through the atomic store.

- Claude Code keeps user-scope MCP servers in ``~/.claude.json`` (JSON) under
  ``mcpServers``.
- Codex keeps them in ``~/.codex/config.toml`` (TOML) under
  ``[mcp_servers.<name>]``.

Both wire Coffer via the stdio shim: ``command = <abs path to coffer-mcp-shim>``.
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any

import tomlkit

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.errors import ConfigFileFormatInvalid

COFFER_SERVER_KEY = "coffer"


def _parse_json(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ConfigFileFormatInvalid("json", str(e)) from e
    if not isinstance(data, dict):
        raise ConfigFileFormatInvalid("json", "top-level value must be an object")
    return data


def _parse_toml(text: str) -> tomlkit.TOMLDocument:
    if not text.strip():
        return tomlkit.document()
    try:
        return tomlkit.parse(text)
    except Exception as e:  # tomlkit raises various ParseError subclasses
        raise ConfigFileFormatInvalid("toml", str(e)) from e


def apply_install(fmt: ConfigFileFormat, text: str, shim_path: str) -> str:
    """Return new config text with the ``coffer`` stdio entry inserted/updated.

    Idempotent: an existing ``coffer`` entry is replaced in place, never
    duplicated.
    """
    if fmt is ConfigFileFormat.JSON:
        data = _parse_json(text)
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            servers = {}
            data["mcpServers"] = servers
        servers[COFFER_SERVER_KEY] = {"command": shim_path}
        # ensure_ascii=False: ~/.claude.json holds the user's whole machine
        # state (project paths, history) which may be non-ASCII; escaping it to
        # \uXXXX on every install needlessly rewrites unrelated content.
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    if fmt is ConfigFileFormat.TOML:
        doc = _parse_toml(text)
        # Recreate `mcp_servers` if absent OR if a hand-edit left a non-table
        # value there — indexing into a scalar/array would raise (mirrors the
        # isinstance(dict) guard the JSON branch uses).
        if not isinstance(doc.get("mcp_servers"), MutableMapping):
            doc["mcp_servers"] = tomlkit.table(is_super_table=True)
        server = tomlkit.table()
        server["command"] = shim_path
        doc["mcp_servers"][COFFER_SERVER_KEY] = server
        return tomlkit.dumps(doc)

    raise AssertionError(f"MCP install unsupported for format {fmt!r}")  # pragma: no cover


def apply_uninstall(fmt: ConfigFileFormat, text: str) -> str:
    """Return new config text with the ``coffer`` entry removed (no-op if absent)."""
    if fmt is ConfigFileFormat.JSON:
        data = _parse_json(text)
        servers = data.get("mcpServers")
        if isinstance(servers, dict):
            servers.pop(COFFER_SERVER_KEY, None)
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    if fmt is ConfigFileFormat.TOML:
        doc = _parse_toml(text)
        servers = doc.get("mcp_servers")
        # isinstance guard: a scalar `mcp_servers` would make `KEY in servers` a
        # substring test and `del servers[KEY]` raise — treat non-tables as "no
        # coffer entry to remove".
        if isinstance(servers, MutableMapping) and COFFER_SERVER_KEY in servers:
            del servers[COFFER_SERVER_KEY]
        return tomlkit.dumps(doc)

    raise AssertionError(f"MCP uninstall unsupported for format {fmt!r}")  # pragma: no cover


def is_installed(fmt: ConfigFileFormat, text: str) -> bool:
    """Whether a ``coffer`` MCP-server entry is present in the config text."""
    if not text.strip():
        return False
    if fmt is ConfigFileFormat.JSON:
        data = _parse_json(text)
        servers = data.get("mcpServers")
        return isinstance(servers, dict) and COFFER_SERVER_KEY in servers
    if fmt is ConfigFileFormat.TOML:
        doc = _parse_toml(text)
        servers = doc.get("mcp_servers")
        # isinstance guard so a scalar `mcp_servers` containing the substring
        # "coffer" can't false-positive via `in`.
        return isinstance(servers, MutableMapping) and COFFER_SERVER_KEY in servers
    raise AssertionError(f"MCP status unsupported for format {fmt!r}")  # pragma: no cover


def installed_command(fmt: ConfigFileFormat, text: str) -> str | None:
    """The ``command`` of the installed coffer entry, or ``None`` if absent."""
    if not is_installed(fmt, text):
        return None
    if fmt is ConfigFileFormat.JSON:
        entry = _parse_json(text)["mcpServers"][COFFER_SERVER_KEY]
        cmd = entry.get("command") if isinstance(entry, dict) else None
        return str(cmd) if cmd is not None else None
    # TOML — the coffer key may map to a scalar (e.g. `coffer = "x"`), which has
    # no `.get`; guard the same way the JSON branch does.
    entry = _parse_toml(text)["mcp_servers"][COFFER_SERVER_KEY]
    cmd = entry.get("command") if isinstance(entry, MutableMapping) else None
    return str(cmd) if cmd is not None else None

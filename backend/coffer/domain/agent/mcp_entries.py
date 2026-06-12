"""Parse / edit the MCP server entries in an agent's own config files.

Pure domain text transforms — no filesystem access. Claude Code keeps JSON
``mcpServers`` maps (``~/.claude.json`` and ``settings.json``); Codex keeps
``[mcp_servers.*]`` tables in ``config.toml``. Parser failures surface as
``AgentConfigParseError`` so the application layer can degrade the listing to
an explicit parse-error state (spec 004 FR-030) instead of failing the view.

``mcp_install.py`` (Coffer's own ``coffer`` entry) imports the shared parse
helpers from here.
"""

from __future__ import annotations

import json
import re
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from typing import Any

import tomlkit

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.errors import (
    AgentConfigParseError,
    ConfigFileFormatInvalid,
    McpEntryNotFound,
)

COFFER_SERVER_KEY = "coffer"
_SECRET_KEY_RE = re.compile(
    r"(TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|CREDENTIAL|AUTHORIZATION)", re.IGNORECASE
)


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


@dataclass(frozen=True)
class McpEntry:
    """One MCP server entry as configured in an agent's own file (derived, never stored)."""

    name: str
    source: str  # allowlist key of the file it came from
    transport: str  # "stdio" | "http"
    command: str | None = None
    args: tuple[str, ...] = ()
    # repr=False: env/header values may contain secrets and must never reach logs
    env: dict[str, str] = field(default_factory=dict, repr=False)
    url: str | None = None
    # repr=False: env/header values may contain secrets and must never reach logs
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    enabled: bool | None = None  # None = format has no per-entry flag (Claude Code)
    is_coffer: bool = False
    matches_resource: str | None = None  # filled by the application layer


def _servers_map(fmt: ConfigFileFormat, text: str) -> MutableMapping[str, Any]:
    try:
        if fmt is ConfigFileFormat.JSON:
            data = _parse_json(text)
            servers = data.get("mcpServers")
        else:
            doc = _parse_toml(text)
            servers = doc.get("mcp_servers")
    except ConfigFileFormatInvalid as e:
        raise AgentConfigParseError("<config>", str(e)) from e
    return servers if isinstance(servers, MutableMapping) else {}


def parse_entries(fmt: ConfigFileFormat, text: str, *, source: str) -> list[McpEntry]:
    """Parse all MCP server entries from ``text`` in the given format.

    Returns an empty list for empty or absent ``mcpServers``/``mcp_servers``
    sections. Raises ``AgentConfigParseError`` on malformed input.
    """
    out: list[McpEntry] = []
    for name, raw in _servers_map(fmt, text).items():
        if not isinstance(raw, MutableMapping):
            continue
        url = raw.get("url")
        headers = raw.get("http_headers") if fmt is ConfigFileFormat.TOML else raw.get("headers")
        enabled: bool | None = None
        if fmt is ConfigFileFormat.TOML:
            enabled = bool(raw.get("enabled", True))
        raw_env = raw.get("env")
        raw_args = raw.get("args")
        # Coerce defensively: non-mapping env/headers → {}, non-list args → ()
        env_map = raw_env if isinstance(raw_env, MutableMapping) else {}
        args_seq = raw_args if isinstance(raw_args, (list, tuple)) else ()
        headers_raw = headers if isinstance(headers, MutableMapping) else {}
        out.append(
            McpEntry(
                name=str(name),
                source=source,
                transport="http" if url is not None else "stdio",
                command=str(raw["command"]) if raw.get("command") is not None else None,
                args=tuple(str(a) for a in args_seq),
                env={str(k): str(v) for k, v in env_map.items()},
                url=str(url) if url is not None else None,
                headers={str(k): str(v) for k, v in headers_raw.items()},
                enabled=enabled,
                is_coffer=str(name) == COFFER_SERVER_KEY,
            )
        )
    return out


def remove_entry(fmt: ConfigFileFormat, text: str, name: str) -> str:
    """Return new config text with the named MCP entry removed.

    Raises ``McpEntryNotFound`` if the entry does not exist.
    Raises ``AgentConfigParseError`` on malformed input.
    """
    if fmt is ConfigFileFormat.JSON:
        try:
            data = _parse_json(text)
        except ConfigFileFormatInvalid as e:
            raise AgentConfigParseError("<config>", str(e)) from e
        servers = data.get("mcpServers")
        if not isinstance(servers, dict) or name not in servers:
            raise McpEntryNotFound(name)
        del servers[name]
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    if fmt is ConfigFileFormat.TOML:
        try:
            doc = _parse_toml(text)
        except ConfigFileFormatInvalid as e:
            raise AgentConfigParseError("<config>", str(e)) from e
        servers = doc.get("mcp_servers")
        if not isinstance(servers, MutableMapping) or name not in servers:
            raise McpEntryNotFound(name)
        del doc["mcp_servers"][name]
        return tomlkit.dumps(doc)

    raise AssertionError(f"remove_entry unsupported for format {fmt!r}")  # pragma: no cover


def set_entry_enabled(text: str, name: str, enabled: bool) -> str:
    """Return new TOML config text with the named entry's ``enabled`` flag set.

    Raises ``McpEntryNotFound`` if the entry does not exist or is not a table.
    Raises ``AgentConfigParseError`` on malformed input.
    """
    try:
        doc = _parse_toml(text)
    except ConfigFileFormatInvalid as e:
        raise AgentConfigParseError("<config>", str(e)) from e
    servers = doc.get("mcp_servers")
    if not isinstance(servers, MutableMapping) or name not in servers:
        raise McpEntryNotFound(name)
    entry = servers[name]
    if not isinstance(entry, MutableMapping):
        raise McpEntryNotFound(name)
    doc["mcp_servers"][name]["enabled"] = enabled
    return tomlkit.dumps(doc)


def secret_env_keys(env: dict[str, str]) -> list[str]:
    """Return sorted list of env keys whose names look like secrets.

    A key is considered secret if its value is non-empty and its name matches
    TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|CREDENTIAL|AUTHORIZATION (case-insensitive).
    """
    return sorted(k for k, v in env.items() if v and _SECRET_KEY_RE.search(k))


def to_transport_config(entry: McpEntry, secret_refs: dict[str, str]) -> dict[str, Any]:
    """Convert an ``McpEntry`` to the transport config dict used by the proxy.

    ``secret_refs`` maps secret env/header key names to their keychain
    reference paths. Secret keys are moved out of the plain ``env``/``headers``
    map and into ``credential_refs``; non-secret keys remain in place.
    """
    if entry.transport == "stdio":
        plain_env = {k: v for k, v in entry.env.items() if k not in secret_refs}
        return {
            "type": "stdio",
            "command": entry.command,
            "args": list(entry.args),
            "env": plain_env,
            "credential_refs": dict(secret_refs),
        }

    # http transport
    plain_headers = {k: v for k, v in entry.headers.items() if k not in secret_refs}
    return {
        "type": "http",
        "url": entry.url,
        "headers": plain_headers,
        "credential_refs": dict(secret_refs),
    }

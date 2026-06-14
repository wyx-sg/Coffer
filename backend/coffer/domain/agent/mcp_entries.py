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

import io
import json
import re
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from typing import Any

import tomlkit
from ruamel.yaml import YAML
from ruamel.yaml import YAMLError as _RuamelYAMLError

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.mcp_injection import default_container_key
from coffer.domain.errors import ConfigFileFormatInvalid
from coffer.domain.workspace_errors import AgentConfigParseError, McpEntryNotFound

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


def _yaml() -> YAML:
    """Round-trip YAML handler (preserves comments/order/quoting), like tomlkit."""
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def _parse_yaml(text: str) -> MutableMapping[str, Any]:
    """Parse YAML to a round-trip mapping. Empty/comment-only text → empty map.

    Raises ``ConfigFileFormatInvalid`` for malformed YAML or a non-mapping top
    level (mirrors the JSON ``top-level value must be an object`` rule).
    """
    if not text.strip():
        return _yaml().load("{}")
    try:
        data = _yaml().load(text)
    except _RuamelYAMLError as e:
        raise ConfigFileFormatInvalid("yaml", str(e)) from e
    if data is None:
        return _yaml().load("{}")
    if not isinstance(data, MutableMapping):
        raise ConfigFileFormatInvalid("yaml", "top-level value must be a mapping")
    return data


def _dump_yaml(data: MutableMapping[str, Any]) -> str:
    buf = io.StringIO()
    _yaml().dump(data, buf)
    return buf.getvalue()


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


def _servers_map(
    fmt: ConfigFileFormat, text: str, container_key: str | None = None
) -> MutableMapping[str, Any]:
    ck = container_key or default_container_key(fmt)
    try:
        if fmt is ConfigFileFormat.JSON:
            servers = _parse_json(text).get(ck)
        elif fmt is ConfigFileFormat.YAML:
            servers = _parse_yaml(text).get(ck)
        else:  # TOML
            servers = _parse_toml(text).get(ck)
    except ConfigFileFormatInvalid as e:
        raise AgentConfigParseError("<config>", str(e)) from e
    return servers if isinstance(servers, MutableMapping) else {}


def _split_command(raw: MutableMapping[str, Any]) -> tuple[str | None, tuple[str, ...]]:
    """Resolve (command, args) from either a string command + args list, or a
    single ``command`` array whose first element is the executable (OpenCode's
    ``command: ["npx", "-y", "pkg"]`` shape)."""
    cmd = raw.get("command")
    extra = raw.get("args")
    extra_args = tuple(str(a) for a in extra) if isinstance(extra, (list, tuple)) else ()
    if isinstance(cmd, (list, tuple)):
        parts = [str(c) for c in cmd]
        if not parts:
            return None, extra_args
        return parts[0], tuple(parts[1:]) + extra_args
    if cmd is None:
        return None, extra_args
    return str(cmd), extra_args


def parse_entries(
    fmt: ConfigFileFormat, text: str, *, source: str, container_key: str | None = None
) -> list[McpEntry]:
    """Parse all MCP server entries from ``text`` in the given format.

    ``container_key`` selects the top-level table (default: the format's
    conventional key — ``mcpServers`` for JSON, ``mcp_servers`` for TOML/YAML;
    agents like OpenCode pass ``mcp``). Handles both the command-map and
    command-array entry shapes and both ``env``/``environment`` key names.
    Returns an empty list for an empty or absent section; raises
    ``AgentConfigParseError`` on malformed input.
    """
    out: list[McpEntry] = []
    for name, raw in _servers_map(fmt, text, container_key).items():
        if not isinstance(raw, MutableMapping):
            continue
        url = raw.get("url")
        headers = raw.get("http_headers") if fmt is ConfigFileFormat.TOML else raw.get("headers")
        # `enabled`: honour an explicit per-entry flag wherever it appears
        # (TOML, plus OpenCode/Hermes). Absent → True for TOML (its historical
        # default), None for formats whose entries carry no flag (Claude/Cursor).
        if "enabled" in raw:
            enabled: bool | None = bool(raw.get("enabled"))
        else:
            enabled = True if fmt is ConfigFileFormat.TOML else None
        command, args_seq = _split_command(raw)
        # env or environment (OpenCode); first non-empty mapping wins
        raw_env = raw.get("env")
        if not isinstance(raw_env, MutableMapping):
            raw_env = raw.get("environment")
        env_map = raw_env if isinstance(raw_env, MutableMapping) else {}
        headers_raw = headers if isinstance(headers, MutableMapping) else {}
        explicit_remote = str(raw.get("type", "")).lower() in {"sse", "http", "remote"}
        out.append(
            McpEntry(
                name=str(name),
                source=source,
                transport="http" if (url is not None or explicit_remote) else "stdio",
                command=command,
                args=args_seq,
                env={str(k): str(v) for k, v in env_map.items()},
                url=str(url) if url is not None else None,
                headers={str(k): str(v) for k, v in headers_raw.items()},
                enabled=enabled,
                is_coffer=str(name) == COFFER_SERVER_KEY,
            )
        )
    return out


def remove_entry(
    fmt: ConfigFileFormat, text: str, name: str, *, container_key: str | None = None
) -> str:
    """Return new config text with the named MCP entry removed.

    ``container_key`` selects the top-level table (default per format). Raises
    ``McpEntryNotFound`` if the entry does not exist, ``AgentConfigParseError``
    on malformed input.
    """
    ck = container_key or default_container_key(fmt)

    if fmt is ConfigFileFormat.JSON:
        try:
            data = _parse_json(text)
        except ConfigFileFormatInvalid as e:
            raise AgentConfigParseError("<config>", str(e)) from e
        servers = data.get(ck)
        if not isinstance(servers, dict) or name not in servers:
            raise McpEntryNotFound(name)
        del servers[name]
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    if fmt is ConfigFileFormat.YAML:
        try:
            data = _parse_yaml(text)
        except ConfigFileFormatInvalid as e:
            raise AgentConfigParseError("<config>", str(e)) from e
        servers = data.get(ck)
        if not isinstance(servers, MutableMapping) or name not in servers:
            raise McpEntryNotFound(name)
        del servers[name]
        return _dump_yaml(data)

    if fmt is ConfigFileFormat.TOML:
        try:
            doc = _parse_toml(text)
        except ConfigFileFormatInvalid as e:
            raise AgentConfigParseError("<config>", str(e)) from e
        servers = doc.get(ck)
        if not isinstance(servers, MutableMapping) or name not in servers:
            raise McpEntryNotFound(name)
        del doc[ck][name]
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

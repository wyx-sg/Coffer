"""Parse / edit the MCP server entries in an agent's own config files.

Pure domain text transforms — no filesystem access. Claude Code keeps JSON
``mcpServers`` maps (``.claude.json`` and ``settings.json``); Codex keeps
``[mcp_servers.*]`` tables in ``config.toml``. Parser failures surface as
``AgentConfigParseError`` so the application layer can degrade the listing to
an explicit parse-error state (spec agent-registry "Degrade a facet to a parse-error
state when its config file is unparseable") instead of failing the view.

``mcp_install.py`` (Coffer's own ``coffer`` entry) imports the shared parse
helpers from here.
"""

from __future__ import annotations

import functools
import json
import re
import tomllib
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Any, Literal

import tomlkit

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.mcp_injection import default_container_key
from coffer.domain.auth_scheme import split_scheme
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


@functools.lru_cache(maxsize=16)
def _read_toml(text: str) -> Mapping[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigFileFormatInvalid("toml", str(e)) from e


def _parse_toml_readonly(text: str) -> Mapping[str, Any]:
    """The TOML ``text`` as plain data, for readers that never edit it.

    ``tomlkit`` keeps the layout a write must preserve, and pays for it: parsing
    a Codex ``config.toml`` with a few dozen servers costs a few hundred
    milliseconds, and the reconciler reads that file several times per pass. A
    read needs none of that, so it takes the standard parser, memoised by
    content — the shared result must not be mutated.
    """
    if not text.strip():
        return {}
    return _read_toml(text)


@dataclass(frozen=True)
class McpEntry:
    """One MCP server entry as configured in an agent's own file (derived, never stored)."""

    name: str
    source: str  # allowlist key of the file it came from
    transport: Literal["stdio", "http"]
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
    cwd: str | None = None  # working directory a stdio server is started in
    # Every other key the entry carries (``type``, ``timeout``, ``env_vars``…),
    # as plain Python values. repr=False for the same reason as env: a format
    # may keep a token here (Codex ``bearer_token``). compare=False: equality
    # is about the server, not about incidental keys a hand-edited file adds.
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)
    # The entry exactly as the file holds it, plain Python (JSON-shaped even for
    # TOML). Holds secret values: only ``redacted_config`` may let it out.
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


#: The keys ``parse_entries`` reads into typed fields; anything else an entry
#: carries lands in ``McpEntry.extra``.
_CONSUMED_KEYS = frozenset(
    {"command", "args", "env", "environment", "url", "headers", "http_headers", "enabled", "cwd"}
)


def _plain(value: Any) -> Any:
    """A tomlkit item (or a JSON value) as plain Python — dict/list/scalars."""
    unwrap = getattr(value, "unwrap", None)
    if callable(unwrap):
        value = unwrap()
    if isinstance(value, MutableMapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _json_container(data: MutableMapping[str, Any], dotted_key: str) -> Any:
    """Resolve a JSON container key that may be a dotted PATH (``mcp.servers``
    — an agent may nest its servers map one level down). Each dot descends one
    object; a missing/non-mapping step resolves to ``None``. Single-segment
    keys behave exactly like a plain ``get``. JSON only — the TOML container
    keys in use carry no dots."""
    node: Any = data
    for part in dotted_key.split("."):
        if not isinstance(node, MutableMapping):
            return None
        node = node.get(part)
    return node


def _servers_map(
    fmt: ConfigFileFormat, text: str, container_key: str | None = None
) -> MutableMapping[str, Any]:
    ck = container_key or default_container_key(fmt)
    try:
        if fmt is ConfigFileFormat.JSON:
            servers = _json_container(_parse_json(text), ck)
        else:  # TOML
            servers = _parse_toml_readonly(text).get(ck)
    except ConfigFileFormatInvalid as e:
        raise AgentConfigParseError("<config>", str(e)) from e
    return servers if isinstance(servers, MutableMapping) else {}


def _split_command(raw: MutableMapping[str, Any]) -> tuple[str | None, tuple[str, ...]]:
    """Resolve (command, args) from either a string command + args list, or a
    single ``command`` array whose first element is the executable
    (``command: [<shim>, ...]``, as a hand-edited config may spell it)."""
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
    conventional key — ``mcpServers`` for JSON, ``mcp_servers`` for TOML;
    agents with a non-default container pass it explicitly, and a dotted JSON
    key like ``mcp.servers`` descends one object per dot). Handles both the
    command-map and command-array entry shapes and both ``env``/``environment``
    key names. Returns an empty list for an empty or absent section; raises
    ``AgentConfigParseError`` on malformed input.
    """
    out: list[McpEntry] = []
    for name, raw in _servers_map(fmt, text, container_key).items():
        if not isinstance(raw, MutableMapping):
            continue
        url = raw.get("url")
        headers = raw.get("http_headers") if fmt is ConfigFileFormat.TOML else raw.get("headers")
        # `enabled`: honour an explicit per-entry flag wherever it appears.
        # Absent → True for TOML (its historical default), None for formats
        # whose entries carry no per-entry flag (e.g. JSON).
        if "enabled" in raw:
            enabled: bool | None = bool(raw.get("enabled"))
        else:
            enabled = True if fmt is ConfigFileFormat.TOML else None
        command, args_seq = _split_command(raw)
        # env or environment (alternate key name); first non-empty mapping wins
        raw_env = raw.get("env")
        if not isinstance(raw_env, MutableMapping):
            raw_env = raw.get("environment")
        env_map = raw_env if isinstance(raw_env, MutableMapping) else {}
        headers_raw = headers if isinstance(headers, MutableMapping) else {}
        explicit_remote = str(raw.get("type", "")).lower() in {"sse", "http", "remote"}
        cwd = raw.get("cwd")
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
                cwd=str(cwd) if cwd is not None else None,
                extra={str(k): _plain(v) for k, v in raw.items() if str(k) not in _CONSUMED_KEYS},
                raw={str(k): _plain(v) for k, v in raw.items()},
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
        servers = _json_container(data, ck)
        if not isinstance(servers, MutableMapping) or name not in servers:
            raise McpEntryNotFound(name)
        del servers[name]
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

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


def secret_env_keys(env: dict[str, str]) -> list[str]:
    """Return sorted list of env keys whose names look like secrets.

    A key is considered secret if its value is non-empty and its name matches
    TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|CREDENTIAL|AUTHORIZATION (case-insensitive).
    """
    return sorted(k for k, v in env.items() if v and _SECRET_KEY_RE.search(k))


def matches_transport(entry: McpEntry, transport: Mapping[str, Any]) -> bool:
    """Equivalence between a config-file entry and a registered resource's transport.

    stdio: same command AND same args; http: same url. Tolerates missing keys.
    """
    if entry.transport == "stdio":
        raw_args = transport.get("args") or []
        args = [str(a) for a in raw_args] if isinstance(raw_args, (list, tuple)) else []
        return (
            transport.get("type") == "stdio"
            and transport.get("command") == entry.command
            and args == list(entry.args)
        )
    return bool(transport.get("type") == "http" and transport.get("url") == entry.url)


def looks_secret(key: str) -> bool:
    """Whether a key NAME looks like it holds a secret (the adopt-time pattern)."""
    return bool(_SECRET_KEY_RE.search(key))


def _holds_secret(value: Any) -> bool:
    """Whether a nested mapping/list carries a secret-looking key anywhere in it."""
    if isinstance(value, dict):
        return any(looks_secret(k) or _holds_secret(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_holds_secret(v) for v in value)
    return False


@dataclass(frozen=True)
class ExtraField:
    """One of an entry's other keys, ready to show: ``value`` is ``None`` when masked."""

    key: str
    value: str | None
    masked: bool


def masked_extra(extra: dict[str, Any]) -> list[ExtraField]:
    """The entry's other keys, sorted, with anything secret-looking withheld.

    A key whose own name looks secret (and whose value is non-empty), or whose
    value nests a secret-looking key at any depth, is masked whole: its value
    never leaves this function. Everything else is rendered as text — strings
    as themselves, other values as compact JSON.
    """
    out: list[ExtraField] = []
    for key in sorted(extra):
        value = extra[key]
        if (looks_secret(key) and value not in (None, "")) or _holds_secret(value):
            out.append(ExtraField(key=key, value=None, masked=True))
            continue
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        out.append(ExtraField(key=key, value=text, masked=False))
    return out


def to_transport_config(entry: McpEntry, secret_refs: dict[str, str]) -> dict[str, Any]:
    """Convert an ``McpEntry`` to the transport config dict used by the proxy.

    ``secret_refs`` maps secret env/header key names to their keychain
    reference paths. Secret keys are moved out of the plain ``env``/``headers``
    map and into ``secret_refs``; non-secret keys remain in place.
    """
    if entry.transport == "stdio":
        plain_env = {k: v for k, v in entry.env.items() if k not in secret_refs}
        return {
            "type": "stdio",
            "command": entry.command,
            "args": list(entry.args),
            "env": plain_env,
            "secret_refs": dict(secret_refs),
        }

    # http transport
    plain_headers = {k: v for k, v in entry.headers.items() if k not in secret_refs}
    # `Authorization: Bearer <key>` stores the key; the scheme stays on the slot.
    schemes = {
        k: scheme
        for k in secret_refs
        if k in entry.headers and (scheme := split_scheme(entry.headers[k])[0])
    }
    return {
        "type": "http",
        "url": entry.url,
        "headers": plain_headers,
        "secret_refs": dict(secret_refs),
        "auth_schemes": schemes,
    }

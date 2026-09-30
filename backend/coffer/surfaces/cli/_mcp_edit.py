"""The config flags of ``coffer mcp edit``.

The same settings the web UI's edit dialog changes — the transport (a stdio
command line or an HTTP URL), its plain env / headers, its credential refs and
the two timeouts — spelled the way ``coffer mcp add`` spells them. Only the
flags given change: the rest of the stored config is carried into the whole
new config the ``PATCH /resources/{uid}`` sends, and the daemon validates the
result against ``MCPServerConfig`` exactly as it does for the web UI's save.

Switching transport (``--http`` on a stdio server or the reverse) is allowed,
as the config schema is a union the daemon re-validates whole; the other
transport's own fields (``command``/``args``/``env``/``cwd`` or
``url``/``headers``) are dropped, while the credential refs are carried over.
"""

from __future__ import annotations

import copy
import inspect
import shlex
from typing import Any, NoReturn

import typer

from coffer.surfaces.cli._kind_verbs import EditFlags


def parse_pairs(flag: str, items: list[str], what: str) -> dict[str, str]:
    """Parse a repeatable ``KEY=VALUE`` flag into a dict (last one wins)."""
    out: dict[str, str] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise typer.BadParameter(f"{flag} must be KEY={what}, got {item!r}")
        out[key] = value
    return out


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(2)


def _retarget(transport: dict[str, Any], kind: str) -> dict[str, Any]:
    """``transport`` as a ``kind`` transport: same type keeps everything, a
    switch keeps only the credential refs."""
    if transport.get("type") == kind:
        return transport
    return {"type": kind, "credential_refs": dict(transport.get("credential_refs") or {})}


def _apply_transport(transport: dict[str, Any], v: dict[str, Any]) -> dict[str, Any]:
    stdio, http = v.get("stdio"), v.get("http")
    if stdio is not None and http is not None:
        _fail("specify at most one of --stdio or --http")
    if stdio is not None:
        parts = shlex.split(stdio)
        if not parts:
            _fail("--stdio command cannot be empty")
        transport = _retarget(transport, "stdio")
        transport["command"], transport["args"] = parts[0], parts[1:]
    elif http is not None:
        transport = _retarget(transport, "http")
        transport["url"] = http
    return transport


def _apply_plain(transport: dict[str, Any], v: dict[str, Any]) -> None:
    """``--env`` / ``--header`` / ``--cwd`` and their clears, each only on the
    transport it belongs to."""
    kind = transport.get("type")
    for flag, key, field, owner in (
        ("--env", "env", "env", "stdio"),
        ("--header", "header", "headers", "http"),
    ):
        pairs, clear = v.get(key) or [], bool(v.get(f"clear_{field}"))
        if not pairs and not clear:
            continue
        if kind != owner:
            _fail(f"{flag} applies to a {owner} server; this one is {kind}")
        merged = {} if clear else dict(transport.get(field) or {})
        merged.update(parse_pairs(flag, pairs, "VALUE"))
        transport[field] = merged
    if v.get("cwd") is not None:
        if kind != "stdio":
            _fail(f"--cwd applies to a stdio server; this one is {kind}")
        transport["cwd"] = v["cwd"] or None


def _apply_credentials(transport: dict[str, Any], v: dict[str, Any]) -> None:
    creds, clear = v.get("credential") or [], bool(v.get("clear_credentials"))
    if not creds and not clear:
        return
    merged = {} if clear else dict(transport.get("credential_refs") or {})
    merged.update(parse_pairs("--credential", creds, "CREDENTIAL_REF"))
    transport["credential_refs"] = merged


_TIMEOUTS = ("spawn_timeout_seconds", "request_timeout_seconds")
_FLAGS = (
    "stdio",
    "http",
    "env",
    "clear_env",
    "header",
    "clear_headers",
    "cwd",
    "credential",
    "clear_credentials",
    *_TIMEOUTS,
)


def mcp_config(resource: dict[str, Any], values: dict[str, Any]) -> dict[str, Any] | None:
    """The stored config with only the flags given applied (``edit``)."""
    if not any(values.get(f) not in (None, False, []) for f in _FLAGS):
        return None
    config = copy.deepcopy(resource.get("config") or {})
    if (config.get("transport") or {}).get("type") == "http_api":
        _fail("this is a custom-tool group; change it with `coffer tool edit` or `tool op edit`")
    transport = _apply_transport(dict(config.get("transport") or {}), values)
    _apply_plain(transport, values)
    _apply_credentials(transport, values)
    config["transport"] = transport
    for key in _TIMEOUTS:
        if values.get(key) is not None:
            config[key] = values[key]
    return config


def _opt(name: str, annotation: Any, default: Any) -> inspect.Parameter:
    return inspect.Parameter(
        name, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=default, annotation=annotation
    )


def _flag(name: str, spelling: str, help_: str) -> inspect.Parameter:
    return _opt(name, bool, typer.Option(False, spelling, help=help_))


def _repeat(name: str, spelling: str, help_: str) -> inspect.Parameter:
    return _opt(name, list[str], typer.Option([], spelling, help=help_))


MCP_EDIT_FLAGS = EditFlags(
    params=(
        _opt(
            "stdio",
            str | None,
            typer.Option(
                None, "--stdio", help="New command line, quoted as one string (stdio transport)"
            ),
        ),
        _opt("http", str | None, typer.Option(None, "--http", help="New URL (http transport)")),
        _repeat("env", "--env", "Plain env var KEY=VALUE for a stdio server (repeatable)"),
        _flag("clear_env", "--clear-env", "Drop every plain env var first"),
        _repeat("header", "--header", "Plain header KEY=VALUE for an http server (repeatable)"),
        _flag("clear_headers", "--clear-headers", "Drop every plain header first"),
        _opt(
            "cwd",
            str | None,
            typer.Option(None, "--cwd", help="Working directory (stdio); empty clears it"),
        ),
        _repeat("credential", "--credential", "ENV_OR_HEADER=CREDENTIAL_REF (repeatable)"),
        _flag("clear_credentials", "--clear-credentials", "Drop every credential ref first"),
        _opt(
            "spawn_timeout_seconds",
            int | None,
            typer.Option(None, "--spawn-timeout-seconds", help="Start-up timeout (5-120)"),
        ),
        _opt(
            "request_timeout_seconds",
            int | None,
            typer.Option(None, "--request-timeout-seconds", help="Per-request timeout (5-1800)"),
        ),
    ),
    to_config=mcp_config,
)

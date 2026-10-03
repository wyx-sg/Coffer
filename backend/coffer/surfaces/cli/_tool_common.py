"""Helpers shared by ``coffer tool`` and ``coffer tool op``."""

from __future__ import annotations

import json
from typing import Any

import httpx
import typer

from coffer.surfaces.cli import _client as _cli_client

#: The fields of a tool a request may write (``CustomToolIn``).
TOOL_FIELDS = (
    "name",
    "description",
    "method",
    "path",
    "headers",
    "body_template",
    "input_schema",
    "enabled",
    "changes_data",
    "operation",
)
_TYPES = {"string", "number", "integer", "boolean", "object", "array"}


def pairs(flag: str, values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in values:
        key, sep, value = raw.partition("=")
        if not sep or not key:
            typer.echo(f"{flag} expects KEY=VALUE, got {raw!r}", err=True)
            raise typer.Exit(2)
        out[key] = value
    return out


def schema_from_args(specs: list[str]) -> dict[str, Any]:
    """``name:type[:required][:description]`` → a JSON Schema object."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for spec in specs:
        parts = spec.split(":", 3)
        name = parts[0].strip()
        kind = (parts[1].strip() if len(parts) > 1 else "") or "string"
        if not name or kind not in _TYPES:
            typer.echo(
                f"--arg expects name:type[:required][:description] with a type of "
                f"{', '.join(sorted(_TYPES))}; got {spec!r}",
                err=True,
            )
            raise typer.Exit(2)
        prop: dict[str, Any] = {"type": kind}
        rest = parts[2:]
        if rest and rest[0].strip() == "required":
            required.append(name)
            rest = rest[1:]
        if rest and rest[0].strip():
            prop["description"] = rest[0].strip()
        properties[name] = prop
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def argument_values(values: list[str], args_json: str | None) -> dict[str, Any]:
    """``--arg-value k=v`` (JSON when it parses) merged over ``--args JSON``."""
    out: dict[str, Any] = {}
    if args_json:
        try:
            loaded = json.loads(args_json)
        except ValueError as e:
            typer.echo(f"--args is not JSON: {e}", err=True)
            raise typer.Exit(2) from e
        if not isinstance(loaded, dict):
            typer.echo("--args must be a JSON object", err=True)
            raise typer.Exit(2)
        out.update(loaded)
    for key, raw in pairs("--arg-value", values).items():
        try:
            out[key] = json.loads(raw)
        except ValueError:
            out[key] = raw
    return out


def get_group(c: httpx.Client, name: str, *, verbose: bool) -> dict[str, Any]:
    r = c.get(f"/custom-tools/{name}")
    _cli_client.check(r, verbose=verbose)
    data: dict[str, Any] = r.json()
    return data


def tool_of(group: dict[str, Any], tool: str) -> dict[str, Any]:
    for t in group.get("tools", []):
        if t["name"] == tool:
            return dict(t)
    typer.echo(f"custom-tool group {group['name']!r} has no tool {tool!r}", err=True)
    raise typer.Exit(4)


def as_tool_in(tool: dict[str, Any]) -> dict[str, Any]:
    """A listed tool as the body a write takes (its flag only when set by hand)."""
    out = {k: tool.get(k) for k in TOOL_FIELDS}
    if not tool.get("changes_data_set", True):
        out["changes_data"] = None
    return out


def header_rows(plain: dict[str, str], secrets: dict[str, str]) -> list[dict[str, Any]]:
    """Group header rows as the API takes them: a value or a secret each."""
    return [
        *({"name": n, "value": v, "secret": None} for n, v in plain.items()),
        *({"name": n, "value": None, "secret": v} for n, v in secrets.items()),
    ]


def print_group(group: dict[str, Any]) -> None:
    typer.echo(f"name:        {group['name']}")
    typer.echo(f"health:      {group['health']}")
    typer.echo(f"base URL:    {group['base_url']}")
    for h in group["headers"]:
        shown = f"<secret {h['secret']}> ({h['secret_state']})" if h["secret"] else h["value"]
        typer.echo(f"header:      {h['name']}: {shown}")
    if group.get("source"):
        src = group["source"]
        typer.echo(f"source:      {src['kind']} {src['location']} (fetched {src['fetched_at']})")
    typer.echo(f"last 24 h:   {group['calls_24h']} calls, {group['failures_24h']} failures")
    typer.echo(
        f"tools:       {sum(1 for t in group['tools'] if t['enabled'])} of {len(group['tools'])} on"
    )
    for t in group["tools"]:
        flags = []
        if not t["enabled"]:
            flags.append("off")
        if t["changes_data"]:
            flags.append("changes data")
        if t.get("reach_override") is not None:
            flags.append("reach override")
        extra = f"  [{', '.join(flags)}]" if flags else ""
        typer.echo(f"  {t['agent_name']:<40} {t['method']:<6} {t['path']}{extra}")

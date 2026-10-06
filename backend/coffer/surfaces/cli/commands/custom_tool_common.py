"""Helpers the ``coffer custom-tool`` modules share: reading a group, header
and variable flags, and printing a group or a test the way the page shows it."""

from __future__ import annotations

from typing import Any

import typer

from coffer.surfaces.cli import _io
from coffer.surfaces.cli._options import ExitCode

GROUPS = "/custom-tools"


def group_path(name: str) -> str:
    return f"{GROUPS}/{name}"


def read_group(name: str, *, as_json: bool) -> dict[str, Any]:
    return dict(_io.call("GET", group_path(name), as_json=as_json))


def environment_of(group: dict[str, Any], env: str, *, as_json: bool) -> dict[str, Any]:
    for e in group.get("environments") or []:
        if e.get("name") == env:
            return dict(e)
    names = ", ".join(e.get("name", "") for e in group.get("environments") or [])
    _io.fail(
        "CUSTOM_TOOL_ENVIRONMENT_NOT_FOUND",
        f"custom-tool group {group.get('name')!r} has no environment {env!r} (it has: {names})",
        ExitCode.NOT_FOUND,
        as_json=as_json,
    )


def pairs(values: list[str] | None, what: str, *, as_json: bool) -> dict[str, str]:
    """``["a=1", "b=2"]`` -> ``{"a": "1", "b": "2"}``."""
    out: dict[str, str] = {}
    for item in values or []:
        key, eq, value = item.partition("=")
        if not eq or not key:
            _io.fail(
                "CLI_INVALID_INPUT",
                f"{what} takes name=value, got {item!r}",
                ExitCode.INVALID_INPUT,
                as_json=as_json,
            )
        out[key] = value
    return out


def header_rows(
    plain: list[str] | None, secret: list[str] | None, *, as_json: bool
) -> list[dict[str, Any]]:
    """``--header Name=value`` and ``--secret-header Name=secret[:Scheme]`` as rows."""
    rows: list[dict[str, Any]] = [
        {"name": k, "value": v} for k, v in pairs(plain, "--header", as_json=as_json).items()
    ]
    for name, ref in pairs(secret, "--secret-header", as_json=as_json).items():
        secret_name, _, scheme = ref.partition(":")
        rows.append({"name": name, "secret": secret_name, "scheme": scheme or None})
    return rows


def rows_of(env: dict[str, Any]) -> list[dict[str, Any]]:
    """An environment's header rows as a request writes them (round-trip)."""
    out: list[dict[str, Any]] = []
    for h in env.get("headers") or []:
        if h.get("secret"):
            out.append({"name": h["name"], "secret": h["secret"], "scheme": h.get("scheme")})
        else:
            out.append({"name": h["name"], "value": h.get("value") or ""})
    return out


def show_group(group: dict[str, Any]) -> None:
    typer.echo(f"{group['name']}  ({'on' if group.get('enabled') else 'off'}, {group['health']})")
    if group.get("description"):
        typer.echo(f"  {group['description']}")
    reach = group.get("scope")
    typer.echo(f"  reach: {'every agent' if reach is None else ', '.join(reach)}")
    typer.echo("  environments:")
    for e in group.get("environments") or []:
        state = "on" if e.get("enabled") else "off"
        typer.echo(f"    {e['name']:<16} {state:<4} {e['base_url']}  secrets: {e['secret_state']}")
        for h in e.get("headers") or []:
            what = f"secret {h['secret']} ({h['secret_state']})" if h.get("secret") else h["value"]
            typer.echo(f"      {h['name']}: {what}")
        for k, v in (e.get("variables") or {}).items():
            typer.echo(f"      {{env:{k}}} = {v}")
    typer.echo("  tools:")
    _io.table(
        [
            {
                "name": t["name"],
                "on": t["enabled"],
                "request": f"{t['method']} {t['path']}",
                "changes_data": t["changes_data"],
            }
            for t in group.get("tools") or []
        ],
        ["name", "on", "request", "changes_data"],
    )
    if group.get("pending_approvals"):
        typer.echo(f"  waiting for approval: {', '.join(group['pending_approvals'])}")


def show_test(result: dict[str, Any]) -> None:
    where = f" [{result['environment']}]" if result.get("environment") else ""
    if result.get("status_line"):
        typer.echo(f"{result['status_line']}{where}  {result.get('url') or ''}")
    else:
        typer.echo(f"not answered ({result.get('failure')}){where}: {result.get('error')}")
    typer.echo(f"{result.get('duration_ms', 0)} ms")
    if result.get("body"):
        typer.echo("")
        typer.echo(result["body"])
    for header, value in (result.get("response_headers") or {}).items():
        typer.echo(f"< {header}: {value}")
    if result.get("truncated"):
        typer.echo("[response cut]")


def show_preview(result: dict[str, Any]) -> None:
    """A dry run: the request a call would send, a secret header by its secret's name."""
    typer.echo(f"{result['method']} {result['url']}  [{result['environment']}]")
    for h in result.get("headers") or []:
        secret = h.get("secret")
        if secret:
            typer.echo(
                f"{h['name']}: {h['value']}  (secret {secret['name']}, id {secret['id']}, "
                f"{secret['state']})"
            )
        else:
            typer.echo(f"{h['name']}: {h['value']}")
    timeout = result.get("timeout_seconds")
    typer.echo(f"timeout: {timeout} s (from the {result.get('timeout_source')})")
    if result.get("body") is not None:
        typer.echo("")
        typer.echo(result["body"])
    typer.echo("\n(dry run: nothing was sent)")


def test_exit(result: dict[str, Any]) -> None:
    """A test whose request failed exits 7, like ``mcp test``."""
    if not result.get("ok"):
        raise typer.Exit(int(ExitCode.UPSTREAM_TEST_FAILED))


def json_arg(value: str | None, what: str, *, as_json: bool) -> Any:
    if value is None:
        return None
    return _io.parse_json(_io.read_text(value, as_json=as_json), what, as_json=as_json)


__all__ = [
    "GROUPS",
    "environment_of",
    "group_path",
    "header_rows",
    "json_arg",
    "pairs",
    "read_group",
    "rows_of",
    "show_group",
    "show_preview",
    "show_test",
    "test_exit",
]

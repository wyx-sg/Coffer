"""``coffer custom-tool group`` / ``import`` / ``reimport`` — the Custom tools page's groups.

Spec mcp-gateway "Manage custom tools from the command line". Every command
calls the daemon's ``/api/v1/custom-tools`` routes (or the kind-agnostic
resource routes the page uses for a group's switch and reach); the gateway, not
this command, calls the upstream API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from coffer.surfaces.cli import _io
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli.commands.custom_tool_common import (
    GROUPS,
    group_path,
    header_rows,
    pairs,
    read_group,
    show_group,
)
from coffer.surfaces.cli.groups import group
from coffer.surfaces.cli.registry import maps

groups = group("custom-tool group")
imports = group("custom-tool import")
reimports = group("custom-tool reimport")
_UI = "Custom tools · "


def _list_rows(value: dict[str, Any]) -> None:
    _io.table(
        [
            {
                "name": g["name"],
                "on": g["enabled"],
                "health": g["health"],
                "environments": ", ".join(e["name"] for e in g.get("environments") or []),
                "tools": len(g.get("tools") or []),
                "secrets": g["secret_state"],
            }
            for g in value.get("groups") or []
        ],
        ["name", "on", "health", "environments", "tools", "secrets"],
    )


@groups.command("list")
@maps("custom-tool group list", ("GET", GROUPS), ui=_UI + "list groups")
def list_groups(as_json: bool = _io.json_option()) -> None:
    """Every group, failing first, with its health, environments and tools."""
    _io.emit(_io.call("GET", GROUPS, as_json=as_json), as_json=as_json, human=_list_rows)


@groups.command("show")
@maps("custom-tool group show", ("GET", GROUPS + "/{name}"), ui=_UI + "open a group")
def show(
    name: str = typer.Argument(..., help="The group's name"), as_json: bool = _io.json_option()
) -> None:
    """A group: its environments with their secrets' state, its tools and reach."""
    _io.emit(read_group(name, as_json=as_json), as_json=as_json, human=show_group)


def _read_document(source: str, *, as_json: bool) -> dict[str, Any]:
    """A URL is fetched by the daemon (through its SSRF guard); a path is read here."""
    if source.startswith(("http://", "https://")):
        return {"url": source}
    path = Path(source).expanduser()
    try:
        return {"document": path.read_text(encoding="utf-8"), "filename": path.name}
    except OSError as e:
        _io.fail(
            "CLI_INVALID_INPUT", f"cannot read {path}: {e}", ExitCode.INVALID_INPUT, as_json=as_json
        )


@groups.command("create")
@maps(
    "custom-tool group create",
    ("POST", GROUPS),
    ("POST", GROUPS + "/openapi"),
    ui=_UI + "add a group (by hand or from an OpenAPI document)",
)
def create(
    name: str = typer.Argument(..., help="The group's name (fixed; prefixes its tools)"),
    env: list[str] | None = typer.Option(
        None, "--env", help="An environment as name=base-URL; repeat for several"
    ),
    base_url: str | None = typer.Option(
        None, "--base-url", help="One environment named 'default' at this URL"
    ),
    header: list[str] | None = typer.Option(
        None, "--header", help="Name=value on every --env (plain, non-secret)"
    ),
    secret_header: list[str] | None = typer.Option(
        None, "--secret-header", help="Name=secret[:Scheme] on every --env"
    ),
    description: str | None = typer.Option(None, "--description", help="What the API is for"),
    timeout: int | None = typer.Option(None, "--timeout", help="Seconds per request (1-300)"),
    agent: list[str] | None = typer.Option(
        None, "--agent", help="Reach only this agent (name or uid); repeat. Default: every agent"
    ),
    from_openapi: str | None = typer.Option(
        None, "--from-openapi", help="An OpenAPI file or URL to draft the tools from"
    ),
    operation: list[str] | None = typer.Option(
        None, "--operation", help="With --from-openapi: an operation key to import; repeat"
    ),
    data: str | None = _io.data_option("The whole group as JSON (text, @file or -)"),
    sets: list[str] | None = _io.set_option(),
    as_json: bool = _io.json_option(),
) -> None:
    """Create a group. A secret binding that waits for approval exits 9 with the
    command that approves it.

    Example: coffer custom-tool group create billing --env test=https://test.example
    --env live=https://api.example --secret-header Authorization=billing-token:Bearer
    """
    body = _io.body_from(data, sets, as_json=as_json, base={"name": name})
    rows = header_rows(header, secret_header, as_json=as_json)
    envs = pairs(env, "--env", as_json=as_json)
    if envs:
        body["environments"] = [
            {"name": n, "base_url": u, "headers": rows} for n, u in envs.items()
        ]
    elif base_url:
        body.update(base_url=base_url, headers=rows)
    if description is not None:
        body["description"] = description
    if timeout is not None:
        body["timeout_seconds"] = timeout
    if agent:
        body["agents"] = [_agent_uid(a, as_json=as_json) for a in agent]
    if from_openapi:
        reading = _io.call(
            "POST",
            GROUPS + "/openapi",
            as_json=as_json,
            body=_read_document(from_openapi, as_json=as_json),
        )
        chosen = set(operation or [op["key"] for op in reading["operations"]])
        unknown = chosen - {op["key"] for op in reading["operations"]}
        if unknown:
            _io.fail(
                "CLI_INVALID_INPUT",
                "no such operation(s) in the document: " + ", ".join(sorted(unknown)),
                ExitCode.INVALID_INPUT,
                as_json=as_json,
            )
        body["tools"] = [op["tool"] for op in reading["operations"] if op["key"] in chosen]
        body["source"] = {
            "kind": reading["source_kind"],
            "location": reading["location"],
            "title": reading.get("title"),
            "version": reading.get("version"),
            "skipped": [op["key"] for op in reading["operations"] if op["key"] not in chosen],
        }
        body.setdefault("description", reading.get("description"))
        if "environments" not in body and "base_url" not in body and reading.get("base_url"):
            body.update(base_url=reading["base_url"], headers=rows)
    if "environments" not in body and "base_url" not in body:
        _io.fail(
            "CLI_INVALID_INPUT",
            "give --env name=URL (repeatable) or --base-url URL",
            ExitCode.INVALID_INPUT,
            as_json=as_json,
        )
    created = _io.call("POST", GROUPS, as_json=as_json, body=body)
    _io.emit(created, as_json=as_json, human=show_group)
    _io.report_pending(created, as_json=as_json)


def _agent_uid(ref: str, *, as_json: bool) -> str:
    from coffer.surfaces.cli import _client
    from coffer.surfaces.cli._resolve import resolve_ref

    client, _ = _client.client_or_exit()
    with client as c:
        return str(resolve_ref(c, "agent", ref)["uid"])


@groups.command("update")
@maps("custom-tool group update", ("PATCH", GROUPS + "/{name}"), ui=_UI + "edit a group")
def update(
    name: str = typer.Argument(..., help="The group's name"),
    description: str | None = typer.Option(None, "--description"),
    timeout: int | None = typer.Option(None, "--timeout", help="The group's seconds per request"),
    data: str | None = _io.data_option(),
    sets: list[str] | None = _io.set_option(),
    as_json: bool = _io.json_option(),
) -> None:
    """Change a group's description or timeout (environments: ``custom-tool env``)."""
    body = _io.body_from(data, sets, as_json=as_json)
    if description is not None:
        body["description"] = description
    if timeout is not None:
        body["timeout_seconds"] = timeout
    changed = _io.call("PATCH", group_path(name), as_json=as_json, body=body)
    _io.emit(changed, as_json=as_json, human=show_group)
    _io.report_pending(changed, as_json=as_json)


@groups.command("delete")
@maps("custom-tool group delete", ("DELETE", GROUPS + "/{name}"), ui=_UI + "delete a group")
def delete(name: str = typer.Argument(...), as_json: bool = _io.json_option()) -> None:
    """Delete a group and its tools; secrets it alone used are released."""
    _io.call("DELETE", group_path(name), as_json=as_json)
    _io.emit({"deleted": name}, as_json=as_json, human=lambda _v: typer.echo(f"deleted: {name}"))


def _switch(name: str, on: bool, *, as_json: bool) -> None:
    uid = read_group(name, as_json=as_json)["uid"]
    answer = _io.call("POST", f"/resources/{uid}/{'enable' if on else 'disable'}", as_json=as_json)
    _io.emit(
        answer, as_json=as_json, human=lambda _v: typer.echo(f"{name}: {'on' if on else 'off'}")
    )


@groups.command("enable")
@maps("custom-tool group enable", ("POST", "/resources/{uid}/enable"), ui=_UI + "switch a group on")
def enable(name: str = typer.Argument(...), as_json: bool = _io.json_option()) -> None:
    """Switch a group on: its tools reach the agents in its reach again."""
    _switch(name, True, as_json=as_json)


@groups.command("disable")
@maps(
    "custom-tool group disable", ("POST", "/resources/{uid}/disable"), ui=_UI + "switch a group off"
)
def disable(name: str = typer.Argument(...), as_json: bool = _io.json_option()) -> None:
    """Switch a group off: no agent sees or calls its tools."""
    _switch(name, False, as_json=as_json)


@groups.command("reach")
@maps("custom-tool group reach", ("PUT", "/resources/{uid}/scope"), ui=_UI + "set a group's reach")
def reach(
    name: str = typer.Argument(...),
    agent: list[str] | None = typer.Option(None, "--agent", help="An agent (name or uid); repeat"),
    every: bool = typer.Option(False, "--all", help="Reach every agent"),
    as_json: bool = _io.json_option(),
) -> None:
    """Choose which agents see the group's tools: ``--agent`` (repeat) or ``--all``."""
    if every == bool(agent):
        _io.fail(
            "CLI_INVALID_INPUT",
            "give --agent (repeatable) or --all",
            ExitCode.INVALID_INPUT,
            as_json=as_json,
        )
    uid = read_group(name, as_json=as_json)["uid"]
    scope = None if every else {"agents": [_agent_uid(a, as_json=as_json) for a in agent or []]}
    answer = _io.call("PUT", f"/resources/{uid}/scope", as_json=as_json, body={"scope": scope})
    _io.emit(answer, as_json=as_json, human=lambda _v: typer.echo(f"{name}: reach set"))


@imports.command("read")
@maps("custom-tool import read", ("POST", GROUPS + "/openapi"), ui=_UI + "read an OpenAPI document")
def import_read(
    url: str | None = typer.Option(None, "--url", help="The document's URL"),
    file: str | None = typer.Option(None, "--file", help="The document's path"),
    as_json: bool = _io.json_option(),
) -> None:
    """Read an OpenAPI document into draft tools; saves nothing."""
    source = url or file
    if not source:
        _io.fail(
            "CLI_INVALID_INPUT", "give --url or --file", ExitCode.INVALID_INPUT, as_json=as_json
        )
    reading = _io.call(
        "POST", GROUPS + "/openapi", as_json=as_json, body=_read_document(source, as_json=as_json)
    )

    def human(r: dict[str, Any]) -> None:
        typer.echo(
            f"{r.get('title') or 'OpenAPI'} {r.get('version') or ''}  base URL: {r.get('base_url')}"
        )
        _io.table(
            [
                {"key": op["key"], "tool": op["tool"]["name"], "summary": op.get("summary")}
                for op in r["operations"]
            ],
            ["key", "tool", "summary"],
        )

    _io.emit(reading, as_json=as_json, human=human)


def _reimport_body(file: str | None, *, as_json: bool) -> dict[str, Any]:
    if file is None:
        return {}
    return {"document": _read_document(file, as_json=as_json).get("document")}


@reimports.command("preview")
@maps(
    "custom-tool reimport preview",
    ("POST", GROUPS + "/{name}/reimport/preview"),
    ui=_UI + "preview a re-import",
)
def reimport_preview(
    name: str = typer.Argument(...),
    file: str | None = typer.Option(
        None, "--file", help="The document again (a file-imported group)"
    ),
    as_json: bool = _io.json_option(),
) -> None:
    """What a re-import would add, remove, keep and change; changes nothing."""
    preview = _io.call(
        "POST",
        group_path(name) + "/reimport/preview",
        as_json=as_json,
        body=_reimport_body(file, as_json=as_json),
    )

    def human(p: dict[str, Any]) -> None:
        typer.echo("add:     " + (", ".join(op["key"] for op in p["added"]) or "-"))
        typer.echo("remove:  " + (", ".join(p["removed"]) or "-"))
        typer.echo("changed: " + (", ".join(c["name"] for c in p.get("changed") or []) or "-"))
        typer.echo("kept:    " + (", ".join(p["kept"]) or "-"))

    _io.emit(preview, as_json=as_json, human=human)


@reimports.command("apply")
@maps(
    "custom-tool reimport apply",
    ("POST", GROUPS + "/{name}/reimport"),
    ui=_UI + "apply a re-import",
)
def reimport_apply(
    name: str = typer.Argument(...),
    file: str | None = typer.Option(None, "--file"),
    add: list[str] | None = typer.Option(
        None, "--add", help="An added operation's key to import; repeat"
    ),
    as_json: bool = _io.json_option(),
) -> None:
    """Apply a re-import: removed tools go, chosen additions arrive switched on,
    kept tools keep their switch, and every environment is kept as it is."""
    body = {**_reimport_body(file, as_json=as_json), "add": list(add or [])}
    applied = _io.call("POST", group_path(name) + "/reimport", as_json=as_json, body=body)
    _io.emit(applied, as_json=as_json, human=show_group)


__all__ = ["groups", "imports", "reimports"]

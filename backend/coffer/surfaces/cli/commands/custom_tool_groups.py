"""``coffer custom-tool group`` — the Custom tools page's groups.

Spec mcp-gateway "Manage custom tools from the command line". Every command
calls the daemon's ``/api/v1/custom-tools`` routes (or the kind-agnostic
resource routes the page uses for a group's switch and reach); the gateway, not
this command, calls the upstream API.
"""

from __future__ import annotations

from typing import Any

import typer

from coffer.surfaces.cli import _io
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli.commands.custom_tool_common import (
    GROUPS,
    group_path,
    header_rows,
    json_arg,
    pairs,
    read_group,
    show_group,
)
from coffer.surfaces.cli.groups import group
from coffer.surfaces.cli.registry import maps

groups = group("custom-tool group")
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


@groups.command("create")
@maps(
    "custom-tool group create",
    ("POST", GROUPS),
    ui=_UI + "add a group",
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
    response: str | None = typer.Option(
        None,
        "--response",
        help='Response settings as JSON {"rules": [...]}: '
        "text, @file or -",
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
    if response is not None:
        body["response"] = json_arg(response, "--response", as_json=as_json)
    if agent:
        body["agents"] = [_agent_uid(a, as_json=as_json) for a in agent]
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
    response: str | None = typer.Option(
        None,
        "--response",
        help='Response settings as JSON {"rules": [...]}: '
        "text, @file or -",
    ),
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
    if response is not None:
        body["response"] = json_arg(response, "--response", as_json=as_json)
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


__all__ = ["groups"]

"""``coffer tool op …`` — one tool (one HTTP request) of a custom-tool group.

Spec mcp-gateway "Manage custom tools on REST and the command line" and
"Switch off or narrow one custom tool". A tool is addressed as ``GROUP TOOL``;
what an agent calls it is ``<group>__<tool>``.
"""

from __future__ import annotations

import json
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import _agent_uids, agent_names, reach_line, verbose_of
from coffer.surfaces.cli._tool_common import (
    argument_values,
    as_tool_in,
    get_group,
    pairs,
    schema_from_args,
    tool_of,
)

op_app = typer.Typer(help="Add, change, switch, narrow and test one tool of a group")

_METHOD = typer.Option(None, "--method", help="GET, POST, PUT, PATCH or DELETE")
_PATH = typer.Option(None, "--path", help="Path template, e.g. /items/{id}?q={q}")
_DESCRIPTION = typer.Option(None, "--description", help="What the agent reads to decide")
_HEADER = typer.Option([], "--header", help="Header KEY=VALUE, may hold {arg} (repeatable)")
_BODY = typer.Option(None, "--body", help="JSON body template with {arg} holes")
_ARG = typer.Option([], "--arg", help="Argument name:type[:required][:description] (repeatable)")
_SCHEMA = typer.Option(None, "--schema", help="The whole argument schema as JSON")
_CHANGES = typer.Option(
    None, "--changes-data/--no-changes-data", help="Mark the tool as changing data (or not)"
)


def _schema(args: list[str], schema: str | None) -> dict[str, Any] | None:
    if schema is not None:
        try:
            parsed = json.loads(schema)
        except ValueError as e:
            typer.echo(f"--schema is not JSON: {e}", err=True)
            raise typer.Exit(2) from e
        return dict(parsed)
    return schema_from_args(args) if args else None


@op_app.command("add")
def add_cmd(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group name"),
    tool: str = typer.Argument(..., help="Tool name (what follows <group>__)"),
    method: str | None = _METHOD,
    path: str | None = _PATH,
    description: str | None = _DESCRIPTION,
    header: list[str] = _HEADER,
    body: str | None = _BODY,
    arg: list[str] = _ARG,
    schema: str | None = _SCHEMA,
    changes_data: bool | None = _CHANGES,
    off: bool = typer.Option(False, "--off", help="Add it switched off"),
) -> None:
    """Add one request by hand to a group, using its base URL and auth."""
    verbose = verbose_of(ctx)
    if path is None:
        typer.echo("--path is required", err=True)
        raise typer.Exit(2)
    payload: dict[str, Any] = {
        "name": tool,
        "description": description or "",
        "method": (method or "GET").upper(),
        "path": path,
        "headers": pairs("--header", header),
        "body_template": body,
        "input_schema": _schema(arg, schema) or {"type": "object", "properties": {}},
        "enabled": not off,
        "changes_data": changes_data,
    }
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/custom-tools/{group}/tools", json=payload)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"added: {group}__{tool}")


@op_app.command("edit")
def edit_cmd(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group name"),
    tool: str = typer.Argument(..., help="Tool name"),
    name: str | None = typer.Option(None, "--name", help="A new tool name"),
    method: str | None = _METHOD,
    path: str | None = _PATH,
    description: str | None = _DESCRIPTION,
    header: list[str] = _HEADER,
    body: str | None = _BODY,
    clear_body: bool = typer.Option(False, "--clear-body", help="Drop the body template"),
    arg: list[str] = _ARG,
    schema: str | None = _SCHEMA,
    changes_data: bool | None = _CHANGES,
) -> None:
    """Change one tool's request; only the options given change (--arg replaces the arguments)."""
    verbose = verbose_of(ctx)
    changes: dict[str, Any] = {}
    for key, value in (("name", name), ("path", path), ("description", description)):
        if value is not None:
            changes[key] = value
    if method is not None:
        changes["method"] = method.upper()
    if header:
        changes["headers"] = pairs("--header", header)
    if body is not None or clear_body:
        changes["body_template"] = None if clear_body else body
    new_schema = _schema(arg, schema)
    if new_schema is not None:
        changes["input_schema"] = new_schema
    if changes_data is not None:
        changes["changes_data"] = changes_data
    if not changes:
        typer.echo("nothing to change", err=True)
        raise typer.Exit(2)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/custom-tools/{group}/tools/{tool}", json=changes)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"updated: {group}__{name or tool}")


@op_app.command("rm")
def rm_cmd(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group name"),
    tool: str = typer.Argument(..., help="Tool name"),
    yes: bool = typer.Option(False, "--yes", "-y", "--force", "-f", help="Do not ask"),
) -> None:
    """Remove one tool from its group."""
    verbose = verbose_of(ctx)
    if not yes and not typer.confirm(f"Remove {group}__{tool}?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/custom-tools/{group}/tools/{tool}")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed: {group}__{tool}")


def _switch(ctx: typer.Context, group: str, tools: list[str], enabled: bool) -> None:
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        for tool in tools:
            r = c.patch(f"/custom-tools/{group}/tools/{tool}", json={"enabled": enabled})
            _cli_client.check(r, verbose=verbose)
            typer.echo(f"{'enabled' if enabled else 'disabled'}: {group}__{tool}")


@op_app.command("enable")
def enable_cmd(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group name"),
    tools: list[str] = typer.Argument(..., help="Tool names"),  # noqa: B008
) -> None:
    """Switch tools on."""
    _switch(ctx, group, tools, True)


@op_app.command("disable")
def disable_cmd(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group name"),
    tools: list[str] = typer.Argument(..., help="Tool names"),  # noqa: B008
) -> None:
    """Switch tools off: agents no longer see or call them."""
    _switch(ctx, group, tools, False)


@op_app.command("scope")
def scope_cmd(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group name"),
    tool: str = typer.Argument(..., help="Tool name"),
    agents: str | None = typer.Option(None, "--agents", help="Narrow to these agents (a,b)"),
    every: bool = typer.Option(False, "--all", help="Reach every agent, later ones too"),
    follow_group: bool = typer.Option(False, "--group", help="Clear the override"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Show or narrow which agents one tool reaches (this machine only)."""
    verbose = verbose_of(ctx)
    if sum([agents is not None, every, follow_group]) > 1:
        typer.echo("pick at most one of --agents / --all / --group", err=True)
        raise typer.Exit(2)
    c, _info = _cli_client.client_or_exit()
    with c:
        if agents is None and not follow_group and not every:
            data = get_group(c, group, verbose=verbose)
        else:
            names = [n.strip() for n in (agents or "").split(",") if n.strip()]
            payload: dict[str, Any] = (
                {"mode": "inherit"}
                if follow_group
                else {"mode": "all"}
                if every
                else {"mode": "chosen", "agents": _agent_uids(c, names, verbose=verbose)}
            )
            r = c.put(f"/custom-tools/{group}/tools/{tool}/reach", json=payload)
            _cli_client.check(r, verbose=verbose)
            data = r.json()
        found = tool_of(data, tool)
        mode = found.get("reach_mode", "inherit")
        override = found.get("reach_override")
        shown = (
            agent_names(c, {"agents": override}, verbose=verbose) if override is not None else None
        )
    if output_json:
        typer.echo(json.dumps({"reach_mode": mode, "reach_override": shown}, indent=2))
        return
    if mode == "all":
        typer.echo("reach: every agent the group reaches, later ones too")
        return
    typer.echo(f"reach: {'follows the group' if shown is None else reach_line(shown)}")


@op_app.command("test")
def test_cmd(
    ctx: typer.Context,
    group: str = typer.Argument(..., help="Group name"),
    tool: str = typer.Argument(..., help="Tool name"),
    arg_value: list[str] = typer.Option(  # noqa: B008
        [], "--arg-value", help="An argument KEY=VALUE, JSON when it parses (repeatable)"
    ),
    args_json: str | None = typer.Option(None, "--args", help="All arguments as a JSON object"),
) -> None:
    """Call one tool once with sample arguments and print the response. Exits 7 on failure."""
    verbose = verbose_of(ctx)
    arguments = argument_values(arg_value, args_json)
    c, _info = _cli_client.client_or_exit()
    with c:
        data = get_group(c, group, verbose=verbose)
        payload = {"tool": as_tool_in(tool_of(data, tool)), "arguments": arguments}
        r = c.post(f"/custom-tools/{group}/test", json=payload)
        _cli_client.check(r, verbose=verbose)
    out = r.json()
    if out.get("error"):
        typer.echo(f"FAIL ({out['duration_ms']} ms): {out['error']}", err=True)
        raise typer.Exit(7)
    typer.echo(f"{out['status_line']}  ({out['duration_ms']} ms)  {out.get('url') or ''}")
    if out["body"]:
        typer.echo(out["body"])
    if not out["ok"]:
        raise typer.Exit(7)

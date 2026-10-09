"""``coffer custom-tool tool`` — one custom tool: add, show, change, switch, test, delete.

Spec mcp-gateway "Manage custom tools from the command line" and "Validate a
custom tool's arguments before any request". A tool's definition comes from
flags, ``--data @tool.json`` or ``--data -``; its argument schema from
``--schema`` (JSON text, ``@file`` or ``-``). Tests name their environment and
go through the daemon, which validates the arguments, resolves only that
environment's secrets and makes the one request. ``--dry-run`` stops before
both: it prints the request a call would send (spec mcp-gateway "Preview a
custom tool's request without sending it") with no secret value read.
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
    set_rules,
    show_group,
    show_preview,
    show_test,
    test_exit,
)
from coffer.surfaces.cli.groups import group
from coffer.surfaces.cli.registry import maps

tools = group("custom-tool tool")
_UI = "Custom tools · "
_TOOL = GROUPS + "/{name}/tools/{tool}"


def _tool_body(
    *,
    data: str | None,
    sets: list[str] | None,
    as_json: bool,
    name: str | None = None,
    method: str | None = None,
    path: str | None = None,
    description: str | None = None,
    header: list[str] | None = None,
    body_template: str | None = None,
    schema: str | None = None,
    changes_data: bool | None = None,
    response_rules: str | None = None,
) -> dict[str, Any]:
    body = _io.body_from(data, sets, as_json=as_json)
    for key, value in (
        ("name", name),
        ("method", method.upper() if method else None),
        ("path", path),
        ("description", description),
        ("changes_data", changes_data),
    ):
        if value is not None:
            body[key] = value
    if header:
        body["headers"] = pairs(header, "--header", as_json=as_json)
    if body_template is not None:
        body["body_template"] = _io.read_text(body_template, as_json=as_json)
    if schema is not None:
        body["input_schema"] = json_arg(schema, "--schema", as_json=as_json)
    set_rules(body, response_rules, as_json=as_json)
    return body


def _find(name: str, tool: str, *, as_json: bool) -> dict[str, Any]:
    found = next((t for t in read_group(name, as_json=as_json)["tools"] if t["name"] == tool), None)
    if found is None:
        _io.fail(
            "CUSTOM_TOOL_NOT_FOUND",
            f"custom-tool group {name!r} has no tool {tool!r}",
            ExitCode.NOT_FOUND,
            as_json=as_json,
        )
    return dict(found)


_M = typer.Option(None, "--method", help="GET, POST, PUT, PATCH or DELETE")
_P = typer.Option(
    None, "--path", help="Path template: /items/{id}?q={q}; {env:NAME} for a variable"
)
_D = typer.Option(None, "--description", help="What the tool does (agents read it)")
_H = typer.Option(None, "--header", help="Name=value header; {argument} holes allowed; repeat")
_B = typer.Option(None, "--body-template", help="JSON body with {argument} holes: text, @file or -")
_S = typer.Option(None, "--schema", help="The arguments' JSON Schema: text, @file or -")
_C = typer.Option(
    None,
    "--changes-data/--read-only",
    help="Whether the tool changes data (default: on for every method but GET)",
)
_R = typer.Option(
    None,
    "--response-rules",
    help="Own response rules, a JSON array (text, @file or -); 'group' follows the group's",
)


@tools.command("list")
@maps("custom-tool tool list", ("GET", GROUPS + "/{name}"), ui=_UI + "a group's Tools tab")
def list_tools(
    name: str = typer.Argument(..., help="The group"), as_json: bool = _io.json_option()
) -> None:
    """A group's tools with their request, switch and 24-hour calls."""
    rows = read_group(name, as_json=as_json)["tools"]
    _io.emit(
        rows,
        as_json=as_json,
        human=lambda r: _io.table(
            [
                {
                    "name": t["name"],
                    "agent_name": t["agent_name"],
                    "on": t["enabled"],
                    "request": f"{t['method']} {t['path']}",
                    "changes_data": t["changes_data"],
                    "calls_24h": t["calls_24h"],
                }
                for t in r
            ],
            ["name", "agent_name", "on", "request", "changes_data", "calls_24h"],
        ),
    )


@tools.command("show")
@maps("custom-tool tool show", ("GET", GROUPS + "/{name}"), ui=_UI + "open a tool")
def show(
    name: str = typer.Argument(...),
    tool: str = typer.Argument(...),
    as_json: bool = _io.json_option(),
) -> None:
    """One tool's definition: request template, headers, body and argument schema."""
    _io.emit(_find(name, tool, as_json=as_json), as_json=as_json)


@tools.command("add")
@maps("custom-tool tool add", ("POST", GROUPS + "/{name}/tools"), ui=_UI + "add a tool")
def add(
    name: str = typer.Argument(..., help="The group"),
    tool: str | None = typer.Option(None, "--name", help="The tool's name"),
    method: str | None = _M,
    path: str | None = _P,
    description: str | None = _D,
    header: list[str] | None = _H,
    body_template: str | None = _B,
    schema: str | None = _S,
    changes_data: bool | None = _C,
    response_rules: str | None = _R,
    data: str | None = _io.data_option("The tool as JSON (text, @file or -)"),
    sets: list[str] | None = _io.set_option(),
    as_json: bool = _io.json_option(),
) -> None:
    """Add a tool. A read-only POST: ``--method POST --read-only``."""
    body = _tool_body(
        data=data,
        sets=sets,
        as_json=as_json,
        name=tool,
        method=method,
        path=path,
        description=description,
        header=header,
        body_template=body_template,
        schema=schema,
        changes_data=changes_data,
        response_rules=response_rules,
    )
    _io.emit(
        _io.call("POST", group_path(name) + "/tools", as_json=as_json, body=body),
        as_json=as_json,
        human=show_group,
    )


@tools.command("update")
@maps("custom-tool tool update", ("PATCH", _TOOL), ui=_UI + "edit a tool")
def update(
    name: str = typer.Argument(...),
    tool: str = typer.Argument(...),
    rename: str | None = typer.Option(None, "--rename", help="A new name for the tool"),
    method: str | None = _M,
    path: str | None = _P,
    description: str | None = _D,
    header: list[str] | None = _H,
    body_template: str | None = _B,
    schema: str | None = _S,
    changes_data: bool | None = _C,
    response_rules: str | None = _R,
    data: str | None = _io.data_option("Fields to change, as JSON (text, @file or -)"),
    sets: list[str] | None = _io.set_option(),
    as_json: bool = _io.json_option(),
) -> None:
    """Change only the fields given (``--header`` replaces every header)."""
    body = _tool_body(
        data=data,
        sets=sets,
        as_json=as_json,
        name=rename,
        method=method,
        path=path,
        description=description,
        header=header,
        body_template=body_template,
        schema=schema,
        changes_data=changes_data,
        response_rules=response_rules,
    )
    _io.emit(
        _io.call("PATCH", f"{group_path(name)}/tools/{tool}", as_json=as_json, body=body),
        as_json=as_json,
        human=show_group,
    )


def _switch(name: str, tool: str, on: bool, *, as_json: bool) -> None:
    answer = _io.call(
        "PATCH", f"{group_path(name)}/tools/{tool}", as_json=as_json, body={"enabled": on}
    )
    _io.emit(
        answer,
        as_json=as_json,
        human=lambda _v: typer.echo(f"{name}__{tool}: {'on' if on else 'off'}"),
    )


@tools.command("enable")
@maps("custom-tool tool enable", ("PATCH", _TOOL), ui=_UI + "switch a tool on")
def enable(
    name: str = typer.Argument(...),
    tool: str = typer.Argument(...),
    as_json: bool = _io.json_option(),
) -> None:
    """Switch a tool on."""
    _switch(name, tool, True, as_json=as_json)


@tools.command("disable")
@maps("custom-tool tool disable", ("PATCH", _TOOL), ui=_UI + "switch a tool off")
def disable(
    name: str = typer.Argument(...),
    tool: str = typer.Argument(...),
    as_json: bool = _io.json_option(),
) -> None:
    """Switch a tool off: hidden from agents, and a call is refused."""
    _switch(name, tool, False, as_json=as_json)


@tools.command("delete")
@maps("custom-tool tool delete", ("DELETE", _TOOL), ui=_UI + "delete a tool")
def delete(
    name: str = typer.Argument(...),
    tool: str = typer.Argument(...),
    as_json: bool = _io.json_option(),
) -> None:
    """Delete a tool."""
    _io.emit(
        _io.call("DELETE", f"{group_path(name)}/tools/{tool}", as_json=as_json),
        as_json=as_json,
        human=show_group,
    )


_E = typer.Option(None, "--env", help="The environment to run it in (needed when several are on)")
_A = typer.Option(None, "--args", help="The arguments as a JSON object: text, @file or -")
_DRY = typer.Option(
    False,
    "--dry-run",
    help="Print the request a call would send — URL, headers, body, timeout — and send "
    "nothing; secret headers show their secret's name, not its value",
)


def _args(value: str | None, *, as_json: bool) -> dict[str, Any]:
    loaded = json_arg(value, "--args", as_json=as_json)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        _io.fail(
            "CLI_INVALID_INPUT",
            "--args must be a JSON object",
            ExitCode.INVALID_INPUT,
            as_json=as_json,
        )
    return dict(loaded)


def _report(result: dict[str, Any], *, as_json: bool) -> None:
    _io.emit(result, as_json=as_json, human=show_test)
    test_exit(result)


@tools.command("test")
@maps(
    "custom-tool tool test",
    ("POST", _TOOL + "/test"),
    ("POST", _TOOL + "/preview"),
    ui=_UI + "test a saved tool",
)
def test(
    name: str = typer.Argument(...),
    tool: str = typer.Argument(...),
    env: str | None = _E,
    args: str | None = _A,
    dry_run: bool = _DRY,
    as_json: bool = _io.json_option(),
) -> None:
    """Run a saved tool once in one environment; saves and logs nothing.

    Invalid arguments are refused before any request (exit 6, one error per
    field); a request the API answers with an error status exits 7.
    ``--dry-run`` prints the request instead of sending it.
    """
    body = {"arguments": _args(args, as_json=as_json), "environment": env}
    path = f"{group_path(name)}/tools/{tool}"
    if dry_run:
        result = _io.call("POST", path + "/preview", as_json=as_json, body=body)
        _io.emit(result, as_json=as_json, human=show_preview)
        return
    _report(_io.call("POST", path + "/test", as_json=as_json, body=body), as_json=as_json)


@tools.command("test-draft")
@maps(
    "custom-tool tool test-draft",
    ("POST", GROUPS + "/{name}/test"),
    ("POST", GROUPS + "/{name}/preview"),
    ui=_UI + "test a tool being edited",
)
def test_draft(
    name: str = typer.Argument(..., help="The group"),
    env: str | None = _E,
    args: str | None = _A,
    dry_run: bool = _DRY,
    response_rules: str | None = _R,
    data: str | None = _io.data_option("The draft tool as JSON (text, @file or -)"),
    sets: list[str] | None = _io.set_option(),
    as_json: bool = _io.json_option(),
) -> None:
    """Run a tool that is not saved, in one of the group's environments.

    ``--dry-run`` prints the request instead of sending it."""
    draft = _io.body_from(data, sets, as_json=as_json)
    set_rules(draft, response_rules, as_json=as_json)
    body = {"tool": draft, "arguments": _args(args, as_json=as_json), "environment": env}
    if dry_run:
        result = _io.call("POST", group_path(name) + "/preview", as_json=as_json, body=body)
        _io.emit(result, as_json=as_json, human=show_preview)
        return
    _report(
        _io.call("POST", group_path(name) + "/test", as_json=as_json, body=body), as_json=as_json
    )


@tools.command("test-unsaved")
@maps(
    "custom-tool tool test-unsaved",
    ("POST", GROUPS + "/test"),
    ui=_UI + "test a request before its group is saved",
)
def test_unsaved(
    base_url: str = typer.Option(..., "--base-url", help="The draft environment's base URL"),
    header: list[str] | None = typer.Option(
        None, "--header", help="Name=value; repeat (no secrets are sent)"
    ),
    var: list[str] | None = typer.Option(None, "--var", help="NAME=value for {env:NAME}; repeat"),
    timeout: int = typer.Option(30, "--timeout"),
    response: str | None = typer.Option(
        None, "--response", help="The draft group's response settings as JSON: text, @file or -"
    ),
    args: str | None = _A,
    data: str | None = _io.data_option("The draft tool as JSON (text, @file or -)"),
    sets: list[str] | None = _io.set_option(),
    as_json: bool = _io.json_option(),
) -> None:
    """Run a request of a group not saved yet: no secret, the URL SSRF-checked."""
    body = {
        "base_url": base_url,
        "headers": header_rows(header, None, as_json=as_json),
        "variables": pairs(var, "--var", as_json=as_json),
        "timeout_seconds": timeout,
        "tool": _io.body_from(data, sets, as_json=as_json),
        "arguments": _args(args, as_json=as_json),
    }
    if response is not None:
        body["response"] = json_arg(response, "--response", as_json=as_json)
    _report(_io.call("POST", GROUPS + "/test", as_json=as_json, body=body), as_json=as_json)


__all__ = ["tools"]

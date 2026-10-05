"""``coffer custom-tool env`` — a group's environments.

Spec mcp-gateway "Keep a custom-tool group's environments in the group" and
"Wait for approval before a custom tool sends its secret". An environment's
header rows are changed by reading the group and sending the whole list back
(``PATCH .../environments/{env}``), exactly as the page's form does; a secret
row names the stored secret and never carries a value. A change that leaves a
binding waiting for approval exits 9 with the command that approves it.
"""

from __future__ import annotations

from typing import Any

import typer

from coffer.surfaces.cli import _io
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli.commands.custom_tool_common import (
    GROUPS,
    environment_of,
    group_path,
    header_rows,
    pairs,
    read_group,
    rows_of,
    show_group,
)
from coffer.surfaces.cli.groups import group
from coffer.surfaces.cli.registry import maps

envs = group("custom-tool env")
_UI = "Custom tools · Environments · "
_ENV = GROUPS + "/{name}/environments/{environment}"


def _env_path(name: str, env: str) -> str:
    return f"{group_path(name)}/environments/{env}"


def _patch(name: str, env: str, body: dict[str, Any], *, as_json: bool) -> None:
    changed = _io.call("PATCH", _env_path(name, env), as_json=as_json, body=body)
    _io.emit(changed, as_json=as_json, human=show_group)
    _io.report_pending(changed, as_json=as_json)


@envs.command("list")
@maps("custom-tool env list", ("GET", GROUPS + "/{name}"), ui=_UI + "list")
def list_envs(
    name: str = typer.Argument(..., help="The group"), as_json: bool = _io.json_option()
) -> None:
    """A group's environments: base URL, switch and the state of their secrets."""
    rows = read_group(name, as_json=as_json)["environments"]
    _io.emit(
        rows,
        as_json=as_json,
        human=lambda r: _io.table(
            [
                {
                    "name": e["name"],
                    "on": e["enabled"],
                    "base_url": e["base_url"],
                    "secrets": e["secret_state"],
                    "waiting": ", ".join(e["pending_approvals"]),
                }
                for e in r
            ],
            ["name", "on", "base_url", "secrets", "waiting"],
        ),
    )


@envs.command("add")
@maps("custom-tool env add", ("POST", GROUPS + "/{name}/environments"), ui=_UI + "add")
def add(
    name: str = typer.Argument(..., help="The group"),
    env: str = typer.Argument(..., help="The new environment's name (any name you choose)"),
    base_url: str = typer.Option(..., "--base-url", help="Where this environment's requests go"),
    header: list[str] | None = typer.Option(None, "--header", help="Name=value (plain); repeat"),
    secret_header: list[str] | None = typer.Option(
        None, "--secret-header", help="Name=secret[:Scheme]: a stored secret's name; repeat"
    ),
    var: list[str] | None = typer.Option(None, "--var", help="NAME=value for {env:NAME}; repeat"),
    timeout: int | None = typer.Option(
        None, "--timeout", help="Seconds per request (default: the group's)"
    ),
    description: str = typer.Option("", "--description"),
    disabled: bool = typer.Option(False, "--disabled", help="Add it switched off"),
    as_json: bool = _io.json_option(),
) -> None:
    """Add an environment to a group; its tools are not copied."""
    body = {
        "name": env,
        "base_url": base_url,
        "headers": header_rows(header, secret_header, as_json=as_json),
        "variables": pairs(var, "--var", as_json=as_json),
        "timeout_seconds": timeout,
        "description": description,
        "enabled": not disabled,
    }
    added = _io.call("POST", group_path(name) + "/environments", as_json=as_json, body=body)
    _io.emit(added, as_json=as_json, human=show_group)
    _io.report_pending(added, as_json=as_json)


@envs.command("update")
@maps("custom-tool env update", ("PATCH", _ENV), ui=_UI + "edit (URL, name, timeout, description)")
def update(
    name: str = typer.Argument(...),
    env: str = typer.Argument(...),
    base_url: str | None = typer.Option(None, "--base-url"),
    rename: str | None = typer.Option(None, "--rename", help="A new name (its approvals are kept)"),
    timeout: int | None = typer.Option(None, "--timeout", help="Its own seconds per request"),
    group_timeout: bool = typer.Option(False, "--group-timeout", help="Use the group's timeout"),
    description: str | None = typer.Option(None, "--description"),
    data: str | None = _io.data_option("Fields to change as JSON (text, @file or -)"),
    sets: list[str] | None = _io.set_option(),
    as_json: bool = _io.json_option(),
) -> None:
    """Change an environment. A new base URL asks again for its secrets' approval."""
    body = _io.body_from(data, sets, as_json=as_json)
    for key, value in (("base_url", base_url), ("name", rename), ("description", description)):
        if value is not None:
            body[key] = value
    if timeout is not None:
        body["timeout_seconds"] = timeout
    if group_timeout:
        body["timeout_seconds"] = None
    _patch(name, env, body, as_json=as_json)


@envs.command("enable")
@maps("custom-tool env enable", ("PATCH", _ENV), ui=_UI + "switch on")
def enable(
    name: str = typer.Argument(...),
    env: str = typer.Argument(...),
    as_json: bool = _io.json_option(),
) -> None:
    """Switch an environment on: callers may choose it again."""
    _patch(name, env, {"enabled": True}, as_json=as_json)


@envs.command("disable")
@maps("custom-tool env disable", ("PATCH", _ENV), ui=_UI + "switch off")
def disable(
    name: str = typer.Argument(...),
    env: str = typer.Argument(...),
    as_json: bool = _io.json_option(),
) -> None:
    """Switch an environment off: a call naming it is refused."""
    _patch(name, env, {"enabled": False}, as_json=as_json)


@envs.command("delete")
@maps("custom-tool env delete", ("DELETE", _ENV), ui=_UI + "delete")
def delete(
    name: str = typer.Argument(...),
    env: str = typer.Argument(...),
    as_json: bool = _io.json_option(),
) -> None:
    """Delete an environment (a group keeps at least one)."""
    _io.emit(
        _io.call("DELETE", _env_path(name, env), as_json=as_json), as_json=as_json, human=show_group
    )


@envs.command("set-header")
@maps("custom-tool env set-header", ("PATCH", _ENV), ui=_UI + "set a header or bind a secret")
def set_header(
    name: str = typer.Argument(...),
    env: str = typer.Argument(...),
    header: str = typer.Argument(..., help="The header's name"),
    value: str | None = typer.Option(None, "--value", help="A plain value"),
    secret: str | None = typer.Option(
        None, "--secret", help="A stored secret's name (its value stays in Coffer)"
    ),
    scheme: str | None = typer.Option(
        None, "--scheme", help="Sent before the secret: Bearer, Basic, Token…"
    ),
    as_json: bool = _io.json_option(),
) -> None:
    """Set one header row of an environment: a plain ``--value``, or ``--secret``
    bound to it (which waits for approval before any request carries it)."""
    if (value is None) == (secret is None):
        _io.fail(
            "CLI_INVALID_INPUT", "give --value or --secret", ExitCode.INVALID_INPUT, as_json=as_json
        )
    current = environment_of(read_group(name, as_json=as_json), env, as_json=as_json)
    rows = [r for r in rows_of(current) if r["name"].lower() != header.lower()]
    rows.append(
        {"name": header, "value": value}
        if secret is None
        else {"name": header, "secret": secret, "scheme": scheme}
    )
    _patch(name, env, {"headers": rows}, as_json=as_json)


@envs.command("unset-header")
@maps("custom-tool env unset-header", ("PATCH", _ENV), ui=_UI + "remove a header")
def unset_header(
    name: str = typer.Argument(...),
    env: str = typer.Argument(...),
    header: str = typer.Argument(...),
    as_json: bool = _io.json_option(),
) -> None:
    """Remove one header row from an environment."""
    current = environment_of(read_group(name, as_json=as_json), env, as_json=as_json)
    rows = [r for r in rows_of(current) if r["name"].lower() != header.lower()]
    _patch(name, env, {"headers": rows}, as_json=as_json)


@envs.command("set-var")
@maps("custom-tool env set-var", ("PATCH", _ENV), ui=_UI + "set a variable")
def set_var(
    name: str = typer.Argument(...),
    env: str = typer.Argument(...),
    var: str = typer.Argument(..., help="The variable's name ({env:NAME} in a tool)"),
    value: str = typer.Argument(..., help="Its value: plain text, never a secret"),
    as_json: bool = _io.json_option(),
) -> None:
    """Set one non-sensitive variable of an environment."""
    current = environment_of(read_group(name, as_json=as_json), env, as_json=as_json)
    _patch(
        name, env, {"variables": {**(current.get("variables") or {}), var: value}}, as_json=as_json
    )


@envs.command("unset-var")
@maps("custom-tool env unset-var", ("PATCH", _ENV), ui=_UI + "remove a variable")
def unset_var(
    name: str = typer.Argument(...),
    env: str = typer.Argument(...),
    var: str = typer.Argument(...),
    as_json: bool = _io.json_option(),
) -> None:
    """Remove one variable from an environment."""
    current = environment_of(read_group(name, as_json=as_json), env, as_json=as_json)
    variables = {k: v for k, v in (current.get("variables") or {}).items() if k != var}
    _patch(name, env, {"variables": variables}, as_json=as_json)


__all__ = ["envs"]

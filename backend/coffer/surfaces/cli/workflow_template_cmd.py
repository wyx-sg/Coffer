"""``coffer workflow template …`` — the shape of the work, from the terminal.

A template is a Resource of kind ``workflow`` (spec workflow FR-001), so these
commands speak to the kind-agnostic resource routes rather than to a template
route of their own — there is no second way to write one. What this module adds
over ``coffer resource`` is only convenience: the kind is implied, and a
definition comes from a file rather than from a shell-quoted JSON blob.

A refusal here is the kind's own validation (FR-006) and names the JSON path of
the offending field, so a bad template is rejected with somewhere to look
rather than with "invalid config".
"""

from __future__ import annotations

import json as _json
import pathlib
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Define the shape of a delivery")
_console = Console()

#: The kind these commands imply, so the person never types it.
_KIND = "workflow"


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def _load_definition(path: str) -> dict[str, Any]:
    file = pathlib.Path(path).expanduser()
    try:
        parsed = _json.loads(file.read_text())
    except OSError as e:
        typer.echo(f"cannot read {file}: {e}", err=True)
        raise typer.Exit(2) from None
    except _json.JSONDecodeError as e:
        typer.echo(f"{file} is not valid JSON: {e}", err=True)
        raise typer.Exit(2) from None
    if not isinstance(parsed, dict):
        typer.echo(f"{file} must hold a JSON object, not {type(parsed).__name__}", err=True)
        raise typer.Exit(2)
    return parsed


@app.command("add")
def add_template(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Template name, e.g. small-change"),
    file: str = typer.Option(..., "--file", "-f", help="JSON definition"),
) -> None:
    """Register a template from a JSON definition."""
    config = _load_definition(file)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/resources", json={"kind": _KIND, "name": name, "config": config})
        _cli_client.check(r, verbose=_verbose(ctx))
    stages = config.get("stages", [])
    typer.echo(f"registered workflow:{name} — {len(stages)} stage(s)")


@app.command("update")
def update_template(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    file: str = typer.Option(..., "--file", "-f", help="JSON definition"),
) -> None:
    """Replace a template's definition.

    A run already created keeps the snapshot it froze, so editing a template
    never disturbs work in flight (FR-010).
    """
    config = _load_definition(file)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/resources/{_KIND}/{name}", json={"config": config})
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"updated workflow:{name}")


@app.command("list")
def list_templates(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Every template this vault holds."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/resources", params={"kind": _KIND})
        _cli_client.check(r, verbose=_verbose(ctx))
        payload = r.json()
    if output_json:
        typer.echo(_json.dumps(payload, indent=2))
        return
    items = payload.get("items", [])
    if not items:
        typer.echo("no templates yet — `coffer workflow template add` registers one")
        return
    table = Table(show_header=True, header_style="bold")
    for column in ("name", "enabled", "stages", "description"):
        table.add_column(column)
    for item in items:
        config = item.get("config") or {}
        table.add_row(
            item["name"],
            "yes" if item.get("enabled", True) else "no",
            " → ".join(
                stage.get("name", stage.get("key", "")) for stage in config.get("stages", [])
            )
            or "—",
            config.get("description", ""),
        )
    _console.print(table)


@app.command("show")
def show_template(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """One template's definition, as stored."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/resources/{_KIND}/{name}")
        _cli_client.check(r, verbose=_verbose(ctx))
        typer.echo(_json.dumps(r.json().get("config", {}), indent=2))


@app.command("rm")
def remove_template(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """Delete a template. Runs created from it are unaffected."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/resources/{_KIND}/{name}")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"deleted workflow:{name}")

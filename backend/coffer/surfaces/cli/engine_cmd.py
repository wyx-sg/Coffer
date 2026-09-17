"""``coffer engine …`` — Coffer's own operating settings, from a terminal.

Two halves of one question, the same two the Settings → Engine page shows:
WHICH MODEL Coffer thinks with (``engine model``), and WHAT IT DOES while
nobody is looking (``engine upkeep``). Both are thin shells over
``/api/v1/internal-engine-config``, so the terminal and the page write the same
row through the same service and record the same audit entry.

The upkeep half is why this group must exist rather than being a page-only
surface (spec internal-engine FR-020/FR-021, ``.agents/sdd.md``): one of the
three passes rewrites the user's own knowledge files on a timer, and an
operator with only a terminal has to be able to switch that off. ``upkeep
list`` therefore names each pass's default interval alongside its chosen one —
an unchosen interval is reported as unchosen, never as a blank where a number
belongs.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Coffer's own engine: the model it thinks with, and its unattended work")
model_app = typer.Typer(help="The model Coffer's own passes run on")
upkeep_app = typer.Typer(help="The passes Coffer runs when nobody asked")
app.add_typer(model_app, name="model")
app.add_typer(upkeep_app, name="upkeep")

_console = Console()

#: The engine's settings singleton. The model and the upkeep rows are read off
#: the same document, which is what makes "what does Coffer do on its own" one
#: answer rather than two that can disagree.
_CONFIG = "/internal-engine-config"


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _get_config(ctx: typer.Context) -> dict[str, Any]:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(_CONFIG)
        _cli_client.check(r, verbose=_verbose(ctx))
    body: dict[str, Any] = r.json()
    return body


def _put(ctx: typer.Context, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.put(path, json=payload)
        _cli_client.check(r, verbose=_verbose(ctx))
    body: dict[str, Any] = r.json()
    return body


@model_app.command("show")
def model_show(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Print the model Coffer's own passes run on."""
    data = _get_config(ctx)
    if output_json:
        typer.echo(
            _json.dumps({"model": data["model"], "updated_at": data["updated_at"]}, indent=2)
        )
        return
    if data["model"] is None:
        typer.echo("no engine model chosen — Coffer's own passes are a clean no-op")
        return
    typer.echo(data["model"])


@model_app.command("set")
def model_set(
    ctx: typer.Context,
    model: str = typer.Argument(..., help="Model id the internal engine should run on"),
) -> None:
    """Choose the model Coffer's own passes run on.

    The ENDPOINT and key come from the connection flagged internal-default
    (``coffer provider internal-default``); only the model is written here.
    """
    data = _put(ctx, _CONFIG, {"model": model})
    typer.echo(f"internal engine model: {data['model']}")


@model_app.command("clear")
def model_clear(ctx: typer.Context) -> None:
    """Forget the engine model, making every internal pass a clean no-op."""
    _put(ctx, _CONFIG, {"model": None})
    typer.echo("internal engine model cleared")


@upkeep_app.command("list")
def upkeep_list(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show each unattended pass's switch, its interval and the default.

    The interval column is the one the operator CHOSE; while they have chosen
    none it reads "default", and the last column says what that default
    actually is — so the terminal shows what the settings page shows.
    """
    upkeep = _get_config(ctx)["upkeep"]
    if output_json:
        typer.echo(_json.dumps(upkeep, indent=2))
        return
    table = Table(title="Unattended passes")
    table.add_column("Pass")
    table.add_column("Enabled")
    table.add_column("Interval")
    table.add_column("Default")
    for name, setting in upkeep.items():
        chosen = f"{setting['interval_s']}s" if setting["interval_s"] is not None else "default"
        table.add_row(
            name,
            "on" if setting["enabled"] else "off",
            chosen,
            f"{setting['default_interval_s']}s",
        )
    _console.print(table)


@upkeep_app.command("set")
def upkeep_set(
    ctx: typer.Context,
    pass_name: str = typer.Argument(..., metavar="PASS", help="aggregate | distil | curate"),
    on: bool = typer.Option(False, "--on", help="Let this pass run"),
    off: bool = typer.Option(False, "--off", help="Stop this pass running"),
    interval: int | None = typer.Option(None, "--interval", help="Seconds between passes"),
    default_interval: bool = typer.Option(
        False, "--default-interval", help="Return this pass to its own default interval"
    ),
) -> None:
    """Change ONE pass's switch or interval, leaving every other pass alone.

    Each half is sent only when named, so a switch can be flipped without
    restating an interval — and an interval below the floor, or a pass Coffer
    does not run, is refused by the same route the page writes through.
    """
    if on and off:
        typer.echo("pick at most one of --on / --off", err=True)
        raise typer.Exit(2)
    if interval is not None and default_interval:
        typer.echo("pick at most one of --interval / --default-interval", err=True)
        raise typer.Exit(2)
    if not (on or off or interval is not None or default_interval):
        typer.echo("nothing to change: pass --on/--off, --interval or --default-interval", err=True)
        raise typer.Exit(2)

    payload: dict[str, Any] = {"pass": pass_name}
    if on or off:
        payload["enabled"] = on
    if interval is not None:
        payload["interval_s"] = interval
    if default_interval:
        payload["use_default_interval"] = True

    setting = _put(ctx, f"{_CONFIG}/upkeep", payload)["upkeep"][pass_name]
    chosen = f"{setting['interval_s']}s" if setting["interval_s"] is not None else "default"
    typer.echo(
        f"{pass_name}: {'on' if setting['enabled'] else 'off'}, every {chosen} "
        f"(default {setting['default_interval_s']}s)"
    )

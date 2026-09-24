"""`coffer daemon features` — list and switch the experimental features.

Unlike ``coffer daemon port``, this goes through the daemon: a
switch takes effect at once, and only the running daemon can make it do so
(spec experimental-features "Switch a feature from the settings page or the
command line"). The daemon writes ``daemon-config.json`` before it answers.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Experimental features on this machine")

_SOURCE_LABEL = {
    "pin": "pinned by COFFER_FEATURES",
    "setting": "set on this machine",
    "channel": "channel default",
}


def _line(feature: dict[str, Any]) -> str:
    state = "on" if feature["enabled"] else "off"
    source = _SOURCE_LABEL.get(feature["source"], feature["source"])
    return f"{feature['key']:<12} {state:<4} ({source})"


@app.command("list")
def list_features(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Every experimental feature, its state, and what decided it."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/daemon/features")
        _cli_client.check(r, verbose=verbose)
        data = r.json()
    if output_json:
        typer.echo(_json.dumps(data))
        return
    typer.echo(f"channel: {data['channel']}")
    for feature in data["features"]:
        typer.echo(_line(feature))


def _switch(ctx: typer.Context, key: str, enabled: bool) -> None:
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.put(f"/daemon/features/{key}", json={"enabled": enabled})
        _cli_client.check(r, verbose=verbose)
        typer.echo(_line(r.json()))


@app.command("enable")
def enable(ctx: typer.Context, key: str = typer.Argument(..., help="Feature key")) -> None:
    """Switch KEY on, at once."""
    _switch(ctx, key, True)


@app.command("disable")
def disable(ctx: typer.Context, key: str = typer.Argument(..., help="Feature key")) -> None:
    """Switch KEY off, at once. Nothing it holds is deleted."""
    _switch(ctx, key, False)

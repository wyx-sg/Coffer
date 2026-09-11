"""``coffer open`` — open the web UI in a browser.

The daemon serves the UI at its own loopback origin (spec mcp-gateway FR-024)
and injects its live API token into the ``index.html`` it serves (FR-025), so a
browser that lands on that origin is authenticated by the act of loading the
page. There is nothing for this command to hand over.

What is left is the part a human cannot do reliably: the port. The daemon binds
the first free port in its range and records it in ``~/.coffer/daemon.json``, so
the origin moves between restarts. This command reads the real one — and
detect-or-spawn starts a daemon if none is running — which is why it still
earns its place.
"""

from __future__ import annotations

import json as _json
import webbrowser

import typer

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Open Coffer's web UI in your browser.")


@app.callback(invoke_without_command=True)
def open_web_ui(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json"),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Print the URL instead of launching a browser.",
    ),
) -> None:
    """Open the UI at the running daemon's origin (detect-or-spawn auto-spawns)."""
    if ctx.invoked_subcommand is not None:
        return

    # client_or_exit is how detect-or-spawn is reached; the client itself is
    # not needed here, so close it rather than leaking its connection pool.
    client, info = _cli_client.client_or_exit()
    client.close()
    url = f"http://127.0.0.1:{info.port}/"

    if output_json:
        typer.echo(_json.dumps({"url": url, "port": info.port}, indent=2))
        return

    if no_browser:
        typer.echo(url)
        return

    if webbrowser.open(url):
        typer.echo(f"opened {url} in your browser")
    else:
        # No browser this process can drive (headless box, SSH session). The
        # URL still works — say so rather than failing.
        typer.echo("could not launch a browser; open this URL yourself:")
        typer.echo(url)

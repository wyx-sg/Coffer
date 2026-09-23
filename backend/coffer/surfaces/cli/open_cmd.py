"""``coffer open`` — open the web UI in a browser.

The daemon serves the UI at its own loopback origin (spec daemon "Serve the
built web UI from the daemon's own origin") and injects its live API token
into the ``index.html`` it serves (spec daemon "Hand the browser its token in
the served page"), so a browser that lands on that origin is authenticated by the act of
loading the page. There is nothing for this command to hand over.

What is left is starting the thing. The port no longer moves — spec daemon
"Bind a fixed, settable port" pinned it to 8000, and a daemon that cannot have it refuses to start
rather than drifting to another one (the 8000-8009 scan survives only behind
the ``COFFER_PORT_RANGE_*`` test override). So this command reads the live port out
of ``~/.coffer/daemon.json`` for correctness rather than for discovery, and what
it actually saves the user is detect-or-spawn: it starts a daemon when none is
running, then opens the page that daemon is serving.
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

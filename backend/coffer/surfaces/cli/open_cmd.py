"""``coffer open`` — open the web UI in a browser, already signed in.

The daemon serves the UI at its own loopback origin (spec 001 FR-024), but a
browser opened at that origin has no API token. This command bridges that: it
holds the token already (via ``~/.coffer/daemon.json``), so it mints a
single-use code and hands it to the browser in the URL **fragment**.

The fragment matters. A query string is sent to the server and shows up in
access logs and referrers; a fragment never leaves the browser. Either way it
is only ever the short-lived single-use code — never the token, which would
land in shell history and browser history for as long as the daemon lives.
"""

from __future__ import annotations

import json as _json
import webbrowser

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._options import ExitCode

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
    """Mint a one-time sign-in code and open the UI (ADR-006 auto-spawns)."""
    if ctx.invoked_subcommand is not None:
        return

    client, info = _cli_client.client_or_exit()
    with client:
        response = client.post("/daemon/web-code")
        if response.status_code != 200:
            typer.echo(f"could not mint a sign-in code: HTTP {response.status_code}", err=True)
            raise typer.Exit(ExitCode.GENERIC)
        code = response.json()["code"]

    url = f"http://127.0.0.1:{info.port}/#code={code}"

    if output_json:
        typer.echo(_json.dumps({"url": url, "port": info.port}, indent=2))
        return

    if no_browser:
        typer.echo(url)
        return

    if webbrowser.open(url):
        typer.echo(f"opened {url.split('#')[0]} in your browser")
    else:
        # No browser this process can drive (headless box, SSH session). The
        # URL still works — say so rather than failing.
        typer.echo("could not launch a browser; open this URL yourself:")
        typer.echo(url)

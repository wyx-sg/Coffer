"""Coffer CLI composition root."""

from __future__ import annotations

import sys

import httpx
import typer

from coffer import __version__
from coffer.surfaces.cli import (
    _client,
    cli_cmd,
    commands,
    config_cmd,
    daemon_cmd,
    groups,
    log_cmd,
    memory_cmd,
    path_cmd,
    proxy_cmd,
    run_cmd,
    secret_cmd,
    vault_cmd,
)
from coffer.surfaces.cli import mcp as mcp_cmd

app = typer.Typer(help="Coffer CLI", no_args_is_help=True)


def _print_version(value: bool) -> None:
    """``--version``: the package version, the same line ``coffer-daemon
    --version`` prints, and exit without reaching any daemon."""
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def root(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show full tracebacks and HTTP request/response context on error.",
    ),
    _version: bool = typer.Option(
        False,
        "--version",
        callback=_print_version,
        is_eager=True,
        help="Print Coffer's version and exit.",
    ),
) -> None:
    """Coffer — local-first AI agent vault."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


groups.set_root(app)
groups.adopt("daemon", daemon_cmd.app)
groups.adopt("config", config_cmd.app)
groups.adopt("log", log_cmd.app)
groups.adopt("path", path_cmd.app)
groups.adopt("mcp", mcp_cmd.app)
groups.adopt("secret", secret_cmd.app)
groups.adopt("cli", cli_cmd.app)
# `coffer run [--secret …] -- cmd`: everything after `--` is the child's argv.
app.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)(run_cmd.run)
groups.adopt("memory", memory_cmd.app)
groups.adopt("proxy", proxy_cmd.app)
groups.adopt("vault", vault_cmd.app)
# Every management command (spec resource-framework "Offer every management
# operation on the command line"): importing a module adds its commands to
# their groups and records their routes in the registry.
commands.load()


def run() -> None:
    """Entry point for the `coffer` script in pyproject.toml.

    A daemon that stops answering after a command built its client surfaces as
    an ``httpx.TransportError`` from wherever the request was made — refused
    before the request, or dropped, reset or timed out during it; it is
    reported here, once, as exit 3 with a message rather than a traceback (spec
    mcp-gateway "Manage MCP servers as resources").
    """
    try:
        app()
    except httpx.TransportError as err:
        sys.exit(int(_client.render_http_error(err, verbose=False)))


if __name__ == "__main__":
    run()

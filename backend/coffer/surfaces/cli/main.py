"""Coffer CLI composition root."""

from __future__ import annotations

import sys

import httpx
import typer

from coffer.surfaces.cli import (
    _client,
    agent_cmd,
    channel_cmd,
    cli_cmd,
    config_cmd,
    daemon_cmd,
    drift_cmd,
    knowledge_cmd,
    log_cmd,
    memory_cmd,
    migrate_cmd,
    open_cmd,
    path_cmd,
    provider_cmd,
    proxy_cmd,
    run_cmd,
    scan_cmd,
    secret_cmd,
    skill_cmd,
    sync_cmd,
    tool_cmd,
    usage_cmd,
    vault_cmd,
)
from coffer.surfaces.cli import mcp as mcp_cmd

app = typer.Typer(help="Coffer CLI", no_args_is_help=True)


@app.callback()
def root(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show full tracebacks and HTTP request/response context on error.",
    ),
) -> None:
    """Coffer — local-first AI agent vault."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


app.add_typer(daemon_cmd.app, name="daemon")
app.add_typer(open_cmd.app, name="open")
app.add_typer(config_cmd.app, name="config")
app.add_typer(log_cmd.app, name="log")
app.add_typer(path_cmd.app, name="path")
app.command("scan")(scan_cmd.scan)
app.add_typer(scan_cmd.adopt_app, name="adopt")
app.add_typer(scan_cmd.discard_app, name="discard")
app.add_typer(mcp_cmd.app, name="mcp")
app.add_typer(tool_cmd.app, name="tool")
app.add_typer(secret_cmd.app, name="secret")
# `coffer run [--secret …] -- cmd`: everything after `--` is the child's argv.
app.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)(run_cmd.run)
app.add_typer(agent_cmd.app, name="agent")
app.add_typer(channel_cmd.app, name="channel")
app.add_typer(skill_cmd.app, name="skill")
app.add_typer(cli_cmd.app, name="cli")
app.add_typer(knowledge_cmd.app, name="knowledge")
app.add_typer(memory_cmd.app, name="memory")
app.add_typer(provider_cmd.app, name="provider")
app.add_typer(proxy_cmd.app, name="proxy")
app.add_typer(usage_cmd.app, name="usage")
app.add_typer(sync_cmd.app, name="sync")
app.add_typer(vault_cmd.app, name="vault")
app.add_typer(drift_cmd.app, name="drift")
app.command("attention")(drift_cmd.attention)
app.command("migrate")(migrate_cmd.migrate_command)


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

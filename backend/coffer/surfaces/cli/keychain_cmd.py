"""coffer keychain — manage OS keychain credentials.

Spec 006: every subcommand goes through the daemon's HTTP API. The CLI never
touches the OS keychain in-process, so the daemon is the sole keychain owner
(creator = reader → silent reads within an app version). The CLI here imports
no credential/keyring code.

Secrets must never appear in logs / audit / structured events. This command
intentionally NEVER logs the value.
"""

from __future__ import annotations

import json as _json
import sys

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._options import ExitCode

app = typer.Typer(help="Manage OS keychain credentials.")
_console = Console()


def _read_value(value: str | None) -> str:
    if value is not None:
        return value
    if sys.stdin.isatty():
        # typer.prompt is untyped (-> Any); coerce to satisfy the str return.
        return str(typer.prompt("Value", hide_input=True, confirmation_prompt=False))
    return sys.stdin.read().rstrip("\n")


@app.command("set")
def set_secret(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Keychain reference key"),
    value: str | None = typer.Option(
        None,
        "--value",
        help=(
            "Provide the secret on the command line "
            "(UNSAFE — visible in shell history; prefer stdin)"
        ),
    ),
) -> None:
    """Store a secret in the OS keychain (via the daemon)."""
    verbose = (ctx.obj or {}).get("verbose", False)
    secret = _read_value(value)
    if not secret:
        typer.echo("empty value rejected", err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT))
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/keychain", json={"ref": ref, "value": secret})
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"stored: {ref}")


@app.command("get")
def get_secret(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Keychain reference key"),
    show: bool = typer.Option(
        False,
        "--show",
        help="Print the actual value (default: redacted)",
    ),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Retrieve a secret from the OS keychain (via the daemon).

    Without ``--show`` only presence is checked (cheap ``/exists`` probe, no
    value leaves the daemon and no read is audited). ``--show`` fetches the
    value via the audited read route.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        if show:
            r = c.get(f"/keychain/{ref}")
            if r.status_code == 404:
                typer.echo(f"not found: {ref}", err=True)
                raise typer.Exit(int(ExitCode.NOT_FOUND))
            _cli_client.check(r, verbose=verbose)
            rendered = r.json()["value"]
        else:
            r = c.get(f"/keychain/{ref}/exists")
            _cli_client.check(r, verbose=verbose)
            if not r.json()["present"]:
                typer.echo(f"not found: {ref}", err=True)
                raise typer.Exit(int(ExitCode.NOT_FOUND))
            rendered = "[redacted]"
    if output_json:
        typer.echo(_json.dumps({"ref": ref, "value": rendered}))
    else:
        typer.echo(rendered)


@app.command("list")
def list_refs(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List known keychain refs (scanned from registered MCP server resources).

    Refs are enumerated from the daemon's registered MCP server configs; each
    ref's presence is then probed via the daemon's ``/keychain/{ref}/exists``
    endpoint (no secret value crosses the API).
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    refs: set[str] = set()
    try:
        c, _info = _cli_client.client_or_exit()
    except SystemExit:
        if output_json:
            typer.echo(_json.dumps({"refs": []}))
        else:
            typer.echo("(no known refs — daemon not reachable to enumerate)")
        return
    presence: dict[str, bool] = {}
    with c:
        r = c.get("/resources", params={"kind": "mcp_server"})
        _cli_client.check(r, verbose=verbose)
        for resource in r.json().get("resources", []):
            config = resource.get("config") or {}
            transport = config.get("transport") or {}
            cred_refs = transport.get("credential_refs") or {}
            refs.update(cred_refs.values())
        if not output_json:
            for ref in refs:
                er = c.get(f"/keychain/{ref}/exists")
                _cli_client.check(er, verbose=verbose)
                presence[ref] = bool(er.json().get("present"))
    if output_json:
        typer.echo(_json.dumps({"refs": sorted(refs)}))
        return
    if not refs:
        typer.echo("(no keychain refs registered in any resource)")
        return
    table = Table(title="Known credential refs")
    table.add_column("Ref")
    table.add_column("Present in keychain")
    for ref in sorted(refs):
        table.add_row(ref, "yes" if presence.get(ref) else "no")
    _console.print(table)


@app.command("delete")
def delete_secret(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Keychain reference key"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
) -> None:
    """Delete a secret from the OS keychain (via the daemon)."""
    if not force and not typer.confirm(f"Delete keychain entry {ref!r}?"):
        raise typer.Exit(int(ExitCode.GENERIC))
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/keychain/{ref}")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"deleted: {ref}")

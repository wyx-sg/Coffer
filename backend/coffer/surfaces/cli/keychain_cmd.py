"""coffer keychain — manage OS keychain credentials.

Direct local access (does NOT go through the daemon); uses
KeyringAdapter for the only allowed import of `keyring`.

Secrets must never appear in logs / audit / structured events.
This command intentionally NEVER calls structlog with the value.
"""

from __future__ import annotations

import json as _json
import sys

import typer
from rich.console import Console
from rich.table import Table

from coffer.domain.errors import CredentialLocked
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
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
    """Store a secret in the OS keychain."""
    adapter = KeyringAdapter()
    try:
        secret = _read_value(value)
        if not secret:
            typer.echo("empty value rejected", err=True)
            raise typer.Exit(int(ExitCode.INVALID_INPUT))
        adapter.set(ref, secret)
    except CredentialLocked as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(int(ExitCode.CREDENTIAL_ISSUE)) from None
    typer.echo(f"stored: {ref}")


@app.command("get")
def get_secret(
    ref: str = typer.Argument(..., help="Keychain reference key"),
    show: bool = typer.Option(
        False,
        "--show",
        help="Print the actual value (default: redacted)",
    ),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Retrieve a secret from the OS keychain."""
    adapter = KeyringAdapter()
    try:
        secret = adapter.get(ref)
    except CredentialLocked as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(int(ExitCode.CREDENTIAL_ISSUE)) from None
    if secret is None:
        typer.echo(f"not found: {ref}", err=True)
        raise typer.Exit(int(ExitCode.NOT_FOUND))
    rendered = secret if show else "[redacted]"
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

    Note: the ``keyring`` API does not expose a list operation on most backends.
    This command enumerates credential refs by scanning the daemon's registered
    MCP server configs. ``keyring`` is then probed per-ref to report presence.
    """
    from coffer.surfaces.cli import _client as _cli_client

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
    with c:
        r = c.get("/resources", params={"kind": "mcp_server"})
        _cli_client.check(r, verbose=verbose)
    for resource in r.json().get("resources", []):
        config = resource.get("config") or {}
        transport = config.get("transport") or {}
        cred_refs = transport.get("credential_refs") or {}
        refs.update(cred_refs.values())
    if output_json:
        typer.echo(_json.dumps({"refs": sorted(refs)}))
        return
    if not refs:
        typer.echo("(no keychain refs registered in any resource)")
        return
    table = Table(title="Known credential refs")
    table.add_column("Ref")
    table.add_column("Present in keychain")
    adapter = KeyringAdapter()
    for ref in sorted(refs):
        try:
            present = adapter.get(ref) is not None
        except CredentialLocked:
            present = False
        table.add_row(ref, "yes" if present else "no")
    _console.print(table)


@app.command("delete")
def delete_secret(
    ref: str = typer.Argument(..., help="Keychain reference key"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
) -> None:
    """Delete a secret from the OS keychain."""
    if not force and not typer.confirm(f"Delete keychain entry {ref!r}?"):
        raise typer.Exit(int(ExitCode.GENERIC))
    adapter = KeyringAdapter()
    adapter.delete(ref)
    typer.echo(f"deleted: {ref}")

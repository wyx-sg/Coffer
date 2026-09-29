"""coffer credentials — manage encrypted credentials (via the daemon).

Secrets are Fernet-encrypted into coffer's database; the master key lives in
``~/.coffer/master.key`` or, opt-in, the OS keychain.  Every subcommand goes
through the daemon's HTTP API; secrets never appear in logs / audit /
structured events.

The daemon is the sole credential owner (creator = reader → silent
reads within an app version). The CLI here imports no credential/keyring code.
Where the master key lives is a setting: ``coffer config get|set
credentials.storage``.
"""

from __future__ import annotations

import json as _json
import sys
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._options import ExitCode

app = typer.Typer(help="Manage encrypted credentials.")
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
    ref: str = typer.Argument(..., help="Credential reference key"),
    value: str | None = typer.Option(
        None,
        "--value",
        help=(
            "Provide the secret on the command line "
            "(UNSAFE — visible in shell history; prefer stdin)"
        ),
    ),
) -> None:
    """Store a secret in the encrypted credential store (via the daemon).

    Without --value the secret is read from stdin, or prompted for. --value
    still stores, but warns that the value lands in your shell history; the
    value itself is never echoed.

    \f
    Spec credentials "Read a secret on the command line without shell history".
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    if value is not None:
        typer.echo(
            "warning: --value puts the secret in your shell history; "
            "pipe it on stdin or omit --value to be prompted instead",
            err=True,
        )
    secret = _read_value(value)
    if not secret:
        typer.echo("empty value rejected", err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT))
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/credentials", json={"ref": ref, "value": secret})
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"stored: {ref}")


@app.command("get")
def get_secret(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Credential reference key"),
    show: bool = typer.Option(
        False,
        "--show",
        help="Print the actual value (default: redacted)",
    ),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Retrieve a secret from the encrypted credential store (via the daemon).

    Without --show it only checks that the secret exists: no value leaves the
    daemon and nothing is audited. --show prints the value, and that read is
    recorded in the audit log.

    \f
    Without ``--show`` only presence is checked (cheap ``/exists`` probe, no
    value leaves the daemon and no read is audited). ``--show`` fetches the
    value via the audited read route.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        if show:
            r = c.get(f"/credentials/{ref}")
            if r.status_code == 404:
                typer.echo(f"not found: {ref}", err=True)
                raise typer.Exit(int(ExitCode.NOT_FOUND))
            _cli_client.check(r, verbose=verbose)
            rendered = r.json()["value"]
        else:
            r = c.get(f"/credentials/{ref}/exists")
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
    """List every credential ref a registered resource cites, with its presence.

    The daemon enumerates refs from every kind (MCP servers, channels, model
    providers, ...) and reports whether the store holds each one; no secret
    value crosses the API.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    try:
        c, _info = _cli_client.client_or_exit()
    except SystemExit:
        if output_json:
            typer.echo(_json.dumps({"refs": []}))
        else:
            typer.echo("(no known refs — daemon not reachable to enumerate)")
        return
    with c:
        r = c.get("/credentials")
        _cli_client.check(r, verbose=verbose)
        refs: list[dict[str, Any]] = r.json().get("refs", [])
    if output_json:
        typer.echo(_json.dumps({"refs": refs}))
        return
    if not refs:
        typer.echo("(no credential refs registered in any resource)")
        return
    table = Table(title="Known credential refs")
    table.add_column("Ref")
    table.add_column("Present in store")
    table.add_column("Cited by")
    for entry in refs:
        cited_by = entry.get("cited_by", [])
        citers = ", ".join(f"{citer['kind']} {citer['name']}" for citer in cited_by)
        table.add_row(entry["ref"], "yes" if entry.get("present") else "no", citers)
    _console.print(table)


@app.command("rm")
def delete_secret(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Credential reference key"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
) -> None:
    """Delete a secret from the encrypted credential store (via the daemon).

    Asks first unless --force is given.

    \f
    Spec credentials "Confirm a command-line delete unless forced".
    """
    if not force and not typer.confirm(f"Delete credential {ref!r}?"):
        raise typer.Exit(int(ExitCode.GENERIC))
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/credentials/{ref}")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"deleted: {ref}")

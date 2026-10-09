"""coffer secret — manage encrypted secrets (via the daemon).

Secrets are Fernet-encrypted into files in the vault; the master key lives in a
signed release's Keychain access group (in a development build, in
``~/.coffer/master.key`` or, opt-in, the OS keychain).  Every subcommand goes
through the daemon's HTTP API; secrets never appear in logs / audit /
structured events.

No command prints a secret's value (spec secret "Return no plaintext on
any route, command or tool"): revealing one takes a present human in the
Coffer desktop app. Writing one stays open — a caller that supplies a value
already has it — except that replacing a value something already receives
waits for approval in the app.

The daemon is the sole secret owner (creator = reader → silent
reads within an app version). The CLI here imports no secret/keyring code.
Where the master key lives is a setting: ``coffer config get|set
secrets.storage``.
"""

from __future__ import annotations

import json as _json
import sys
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.domain.secrets import secret_uri
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import _io
from coffer.surfaces.cli._options import ExitCode

app = typer.Typer(help="Manage encrypted secrets.")
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
    ref: str | None = typer.Argument(
        None, help="An existing secret's reference, to replace its value"
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        help="Create a new secret with this label; Coffer mints its id",
    ),
    description: str | None = typer.Option(
        None,
        "--description",
        help="With --name: what the new secret is for",
    ),
    value: str | None = typer.Option(
        None,
        "--value",
        help=(
            "Provide the secret on the command line "
            "(UNSAFE — visible in shell history; prefer stdin)"
        ),
    ),
    as_json: bool = _io.json_option(),
) -> None:
    """Create a secret with `--name "<label>"` (and `--description`), or replace one by ref.

    A new secret is given a label by you and an id by Coffer: the command
    prints its ref and `coffer://secret/<id>`, which is how files cite it.
    `coffer secret set <ref>` only replaces the value of a secret that exists.

    Without --value the secret is read from stdin, or prompted for. --value
    still stores, but warns that the value lands in your shell history; the
    value itself is never echoed. --json prints the ref and its URI (and the
    --value warning), never the value; a failure is the shared JSON error.

    \f
    Spec secret "Read a secret on the command line without shell history".
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    if (ref is None) == (name is None):
        _io.fail(
            "CLI_INVALID_INPUT",
            'give --name "<label>" to create a secret, or a ref to replace one',
            ExitCode.INVALID_INPUT,
            as_json=as_json,
        )
    if description is not None and name is None:
        _io.fail(
            "CLI_INVALID_INPUT",
            "--description goes with --name, for a new secret",
            ExitCode.INVALID_INPUT,
            as_json=as_json,
        )
    warning = None
    if value is not None:
        warning = (
            "--value puts the secret in your shell history; "
            "pipe it on stdin or omit --value to be prompted instead"
        )
        if not as_json:
            typer.echo(f"warning: {warning}", err=True)
    secret = _read_value(value)
    if not secret:
        _io.fail(
            "CLI_INVALID_INPUT", "empty value rejected", ExitCode.INVALID_INPUT, as_json=as_json
        )
    with _io.client(as_json=as_json) as c:
        if ref is not None:
            found = c.get(f"/secrets/{ref}/exists")
            _cli_client.check(found, verbose=verbose, as_json=as_json)
            if not found.json().get("present"):
                _io.fail(
                    "CLI_INVALID_INPUT",
                    f'no secret {ref!r}: create one with --name "<label>" (Coffer mints the id)',
                    ExitCode.INVALID_INPUT,
                    as_json=as_json,
                    details={"ref": ref},
                )
            r = c.post("/secrets", json={"ref": ref, "value": secret})
            _cli_client.check(r, verbose=verbose, as_json=as_json)
            stored = {"status": "stored", "ref": ref, "uri": secret_uri(ref)}
        else:
            body = {"label": name, "value": secret}
            if description:
                body["description"] = description
            r = c.post("/secrets", json=body)
            _cli_client.check(r, verbose=verbose, as_json=as_json)
            minted = r.json()
            stored = {"status": "stored", "ref": minted["ref"], "uri": minted["uri"]}
    if as_json:
        # The ref and how to cite it — never the value.
        _io.emit({**stored, **({"warning": warning} if warning else {})}, as_json=True)
        return
    typer.echo(f"stored: {stored['ref']}")
    if ref is None:
        typer.echo(f"cite it as: {stored['uri']}")


@app.command("list")
def list_refs(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List every stored secret and every ref a resource cites.

    Shows whether the store holds each one, what uses it (resources, skills
    citing coffer://secret/<name>), unreferenced ones, and whether another
    process on this Mac can read it where Coffer puts it. No value crosses
    the API.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    with _io.client(as_json=output_json) as c:
        r = c.get("/secrets")
        _cli_client.check(r, verbose=verbose, as_json=output_json)
        refs: list[dict[str, Any]] = r.json().get("refs", [])
    if output_json:
        typer.echo(_json.dumps({"refs": refs}))
        return
    if not refs:
        typer.echo("(no secret refs registered in any resource)")
        return
    table = Table(title="Secrets")
    table.add_column("Label")
    table.add_column("Ref")
    table.add_column("Present in store")
    table.add_column("Used by")
    table.add_column("Readable by local processes")
    for entry in refs:
        cited_by = entry.get("cited_by", [])
        used = [f"{citer['kind']} {citer['name']}" for citer in cited_by]
        used += [f"skill {name}" for name in entry.get("mentioned_by_skills", [])]
        pending = [b for b in entry.get("bindings", []) if b.get("status") == "pending"]
        if pending:
            used.append(f"{len(pending)} waiting for approval")
        table.add_row(
            entry.get("label") or "",
            entry["ref"],
            "yes" if entry.get("present") else "no",
            ", ".join(used) or "(unreferenced)",
            "yes" if entry.get("readable_by_local_processes") else "no",
        )
    _console.print(table)

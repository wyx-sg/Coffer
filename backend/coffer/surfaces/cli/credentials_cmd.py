"""coffer credentials — manage encrypted credentials (via the daemon).

Secrets are Fernet-encrypted into coffer's database; the master key lives in a
signed release's Keychain access group (in a development build, in
``~/.coffer/master.key`` or, opt-in, the OS keychain).  Every subcommand goes
through the daemon's HTTP API; secrets never appear in logs / audit /
structured events.

No command prints a secret's value (spec credentials "Return no plaintext on
any route, command or tool"): revealing one takes a present human in the
Coffer desktop app. Writing one stays open — a caller that supplies a value
already has it — except that replacing a value something already receives
waits for approval in the app.

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
from coffer.surfaces.cli._approvals import WAIT_OPTION, settle
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
    wait: bool = WAIT_OPTION,
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
        if r.status_code == 202:
            # The value replaces one an approved destination receives: it waits,
            # sealed, for the Coffer app (spec credentials "Hold a replaced
            # value in use until a person approves it").
            settle(c, [r.json()["approval"]], wait=wait, verbose=verbose)
    typer.echo(f"stored: {ref}")


@app.command("get")
def get_secret(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Credential reference key"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Check that a secret is stored, without its value.

    Prints [redacted] when it is, exits 4 when it is not. No value leaves the
    daemon and nothing is audited. To see a value, open the Coffer desktop app:
    it asks for Touch ID or your password each time.

    \f
    Spec credentials "Check a secret's presence on the command line".
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/credentials/{ref}/exists")
        _cli_client.check(r, verbose=verbose)
        if not r.json()["present"]:
            typer.echo(f"not found: {ref}", err=True)
            raise typer.Exit(int(ExitCode.NOT_FOUND))
    if output_json:
        typer.echo(_json.dumps({"ref": ref, "present": True, "value": "[redacted]"}))
    else:
        typer.echo("[redacted]")


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
    table = Table(title="Credentials")
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
            entry["ref"],
            "yes" if entry.get("present") else "no",
            ", ".join(used) or "(unreferenced)",
            "yes" if entry.get("readable_by_local_processes") else "no",
        )
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


@app.command("approvals")
def list_approvals(
    ctx: typer.Context,
    all_: bool = typer.Option(False, "--all", help="Include decided approvals"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List what waits for approval in the Coffer app.

    Approving takes Touch ID or your password in the desktop app; the terminal
    can only list and reject.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        params = {} if all_ else {"status": "pending"}
        r = c.get("/credentials/approvals", params=params)
        _cli_client.check(r, verbose=verbose)
        rows: list[dict[str, Any]] = r.json().get("approvals", [])
    if output_json:
        typer.echo(_json.dumps({"approvals": rows}))
        return
    if not rows:
        typer.echo("(nothing waits for approval)")
        return
    table = Table(title="Approvals")
    for col in ("Id", "Status", "What", "Requested by"):
        table.add_column(col)
    for a in rows:
        table.add_row(a["id"], a["status"], a["description"], a["requested_by"])
    _console.print(table)


@app.command("reject")
def reject_approval(
    ctx: typer.Context,
    approval_id: str = typer.Argument(..., help="Approval id (see `coffer credentials approvals`)"),
) -> None:
    """Refuse a pending approval. Refusing needs no presence check."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/credentials/approvals/{approval_id}/reject")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"rejected: {approval_id}")


@app.command("scan")
def scan_plaintext(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
    prompt: bool = typer.Option(
        False,
        "--prompt",
        help="Print the prompt that hands rewriting skills still reading ~/.coffer/secrets/ "
        "to an agent",
    ),
) -> None:
    """Find plaintext secrets in ~/.coffer/secrets/ and in your skills.

    Prints where each one is and the name it would get — never the value.
    Move them into the encrypted store with `coffer credentials import`.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/credentials/scan")
        _cli_client.check(r, verbose=verbose)
        body = r.json()
    if output_json:
        typer.echo(_json.dumps(body))
        return
    if prompt:
        handoff = body.get("handoff")
        typer.echo(handoff["prompt"] if handoff else "(no skill reads ~/.coffer/secrets/)")
        return
    findings = body.get("findings", [])
    if not findings:
        typer.echo("(no plaintext secrets found)")
    else:
        table = Table(title="Plaintext secrets")
        for col in ("Id", "File", "Key", "Would become"):
            table.add_column(col)
        for f in findings:
            where = f"{f['path']}:{f['line']}" if f["line"] else f["path"]
            table.add_row(f["id"], where, f["key"], f"coffer://secret/{f['proposed_name']}")
        _console.print(table)
    for m in body.get("mentions", []):
        typer.echo(
            f"skill {m['skill']} still reads {m['mention']} ({m['path']}:{m['line']}) — "
            "move its command to `coffer run --secret` or `coffer run --env-file`"
        )
    if body.get("handoff"):
        typer.echo("`coffer credentials scan --prompt` hands rewriting them to an agent")


@app.command("import")
def import_plaintext(
    ctx: typer.Context,
    ids: list[str] = typer.Option(  # noqa: B008
        [], "--id", help="Only this finding (repeatable; default: every finding)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the plan and write nothing"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt"),
) -> None:
    """Move plaintext secrets into the encrypted store, leaving references.

    Each value is stored as coffer://secret/<name>, read back and compared,
    and only then replaced in its file by the reference. No plaintext backup
    is kept.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    if not dry_run and not yes and not typer.confirm("Move these secrets into the store?"):
        raise typer.Exit(int(ExitCode.GENERIC))
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/credentials/import", json={"ids": ids or None, "dry_run": dry_run})
        _cli_client.check(r, verbose=verbose)
        body = r.json()
    verb = "would move" if dry_run else "moved"
    for m in body.get("moved", []):
        typer.echo(f"{verb}: {m['path']} → {m['uri']}")
    for sk in body.get("skipped", []):
        typer.echo(f"skipped: {sk['path']} ({sk['reason']})", err=True)

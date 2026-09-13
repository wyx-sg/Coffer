"""coffer sync ... commands (spec vault-sync).

Configure the one git remote this vault converges with, run a round by hand,
answer a held one, look at the fleet, and bootstrap the master key.

There is no ``export`` or ``import`` here. Writing a bundle to a directory and
reading one back was a wholesale overwrite with no base, and it has no place
beside the diff-based round. What replaces it needs no Coffer command: a new
machine runs ``coffer sync adopt``, an offline medium is a ``file://`` remote on
a USB drive, and handing a copy to someone else is ``git clone ~/.coffer/sync``.
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console

from coffer.domain.sync.backup import DEFAULT_BRANCH, DEFAULT_INTERVAL_SECONDS
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.sync_machine_cmd import key_app, machine_app

app = typer.Typer(help="Keep this vault converged with a git remote you own")
remote_app = typer.Typer(help="The one git remote this vault converges with")
app.add_typer(remote_app, name="remote")
app.add_typer(machine_app, name="machine")
app.add_typer(key_app, name="key")

_console = Console()

#: Statuses that mean the user has something to do.
_NEEDS_ATTENTION = frozenset({"conflict", "awaiting_confirmation", "push_failed", "failed"})


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def _counts(label: str, counts: dict[str, Any]) -> str:
    parts = [f"{k} {v}" for k, v in counts.items() if v]
    return f"{label}: {', '.join(parts)}" if parts else f"{label}: nothing"


def _print_round(run: dict[str, Any]) -> None:
    status = run.get("status", "?")
    style = "yellow" if status in _NEEDS_ATTENTION else "green"
    _console.print(f"[{style}]{status}[/{style}]")

    if run.get("join"):
        joined = run["join"]
        _console.print(
            f"  joined this remote as a [bold]{joined}[/bold] machine"
            + (
                "  (its id was already in the registry, so its base came from its own descriptor)"
                if joined == "returning"
                else ""
            )
        )
    _console.print("  " + _counts("applied here", run.get("applied") or {}))
    _console.print("  " + _counts("published", run.get("published") or {}))
    if run.get("commit"):
        _console.print(f"  commit: {run['commit'][:12]}")

    for path in run.get("agent_resolved") or []:
        _console.print(f"  [cyan]merged by agent[/cyan]: {path}  (worth a look)")
    for path in run.get("conflicts") or []:
        _console.print(f"  [yellow]conflict[/yellow]: {path}")
    if run.get("conflicts"):
        _console.print("  resolve them with your own git tools, then run 'coffer sync now'")
    for failure in run.get("failures") or []:
        _console.print(f"  [red]could not apply[/red] {failure['path']}: {failure['reason']}")
    for ref in run.get("locked_refs") or []:
        _console.print(f"  [yellow]credential locked[/yellow]: {ref}")
    if run.get("locked_refs"):
        _console.print("  run 'coffer sync key import <path>' to unlock them")

    pending = run.get("pending")
    if pending:
        _print_pending(pending)
    if run.get("error"):
        _console.print(f"  [red]{run['error']}[/red]")


def _print_pending(pending: dict[str, Any]) -> None:
    direction = pending.get("direction")
    if direction == "publish":
        _console.print(
            "  [yellow]held[/yellow]: this round would delete the following from the remote."
        )
        _console.print("  If this vault was just reinstalled or restored, do NOT confirm.")
    else:
        _console.print("  [yellow]held[/yellow]: this round would delete the following locally.")
    for area, deleted, total in (tuple(b.values()) for b in pending.get("breaches") or []):
        _console.print(f"    {area}: {deleted} of {total}")
    for path in (pending.get("paths") or [])[:20]:
        _console.print(f"    - {path}")
    extra = len(pending.get("paths") or []) - 20
    if extra > 0:
        _console.print(f"    … and {extra} more")
    _console.print("  'coffer sync confirm' to proceed, 'coffer sync reject' to discard")


# --- rounds -----------------------------------------------------------------


@app.command("now")
def sync_now(ctx: typer.Context) -> None:
    """Converge with the remote once, right now."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/run", json={})
        _cli_client.check(r, verbose=verbose)
        _print_round(r.json())


@app.command("adopt")
def adopt(
    ctx: typer.Context,
    url: str = typer.Argument(None, help="Remote to configure first, if not already set"),
    keep_local: bool = typer.Option(
        False,
        "--keep-local",
        help=(
            "Only for a machine that synced here before and whose recorded base is gone: "
            "publish this vault's documents as additions instead of refusing"
        ),
    ),
) -> None:
    """Join the remote. A new machine takes the union; a returning one recovers its base."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        if url:
            r = c.put("/sync/remote", json={"url": url})
            _cli_client.check(r, verbose=verbose)
        body = {"choice": "keep-local"} if keep_local else {}
        r = c.post("/sync/adopt", json=body)
        _cli_client.check(r, verbose=verbose)
        _print_round(r.json())


@app.command("confirm")
def confirm(ctx: typer.Context) -> None:
    """Accept a round the deletion guard held, and let it finish."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/confirm", json={})
        _cli_client.check(r, verbose=verbose)
        _print_round(r.json())


@app.command("reject")
def reject(ctx: typer.Context) -> None:
    """Discard a held round. The vault was never touched."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/reject", json={})
        _cli_client.check(r, verbose=verbose)
    _console.print("[green]discarded[/green] — the vault is unchanged")


@app.command("rebuild")
def rebuild(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt"),
) -> None:
    """Rebuild this machine from the remote, discarding what only it holds.

    For a machine whose vault is gone: confirming a held round would publish
    the loss to every other machine, and rejecting would refuse the same round
    forever. This is the third answer, and it throws away local-only documents.
    """
    if not yes:
        typer.confirm(
            "This replaces this machine's vault with the remote's, discarding "
            "anything only this machine has. Continue?",
            abort=True,
        )
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/rebuild", json={})
        _cli_client.check(r, verbose=verbose)
        _print_round(r.json())


@app.command("rollback")
def rollback(ctx: typer.Context) -> None:
    """Undo the last applied round from its pre-apply snapshot."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/rollback", json={})
        _cli_client.check(r, verbose=verbose)
        _print_round(r.json())


@app.command("restore")
def restore(
    ctx: typer.Context,
    at: str = typer.Option(
        None, "--at", help="A sha, a ref, or YYYY-MM-DD — the last commit at or before it"
    ),
) -> None:
    """Bring the vault to an earlier point in the remote's history."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/restore", json={"at": at})
        _cli_client.check(r, verbose=verbose)
        _print_round(r.json())


@app.command("status")
def status(ctx: typer.Context) -> None:
    """What the remote is, and how the last round went."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/sync/status")
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
    if not payload.get("configured"):
        _console.print("no sync remote configured — 'coffer sync remote set <url>'")
    else:
        _print_remote(payload["remote"])
    _console.print(f"this machine: {payload.get('machine_id')}")
    if not payload.get("machine_id_is_derived"):
        _console.print(
            "  [yellow]note[/yellow]: this id is stored locally, not derived from the host, "
            "so deleting ~/.coffer makes this machine reappear as a new one"
        )
    last = payload.get("last_run")
    if last is None:
        _console.print("no round yet")
    else:
        _print_round(last)


# --- remote -----------------------------------------------------------------


def _print_remote(remote: dict[str, Any]) -> None:
    _console.print(f"remote: {remote['url']}  branch {remote['branch']}")
    _console.print(
        f"  every {remote['interval_seconds']}s · "
        f"credentials {'included' if remote['include_credentials'] else 'excluded'} · "
        f"{'enabled' if remote['enabled'] else 'disabled'}"
    )
    if remote.get("credential_ref"):
        _console.print(f"  push credential: {remote['credential_ref']}")
    _console.print(f"  working tree: {remote['worktree_path']}")


@remote_app.command("set")
def remote_set(
    ctx: typer.Context,
    url: str = typer.Argument(..., help="Git remote URL you own (https, ssh, or file://)"),
    branch: str = typer.Option(DEFAULT_BRANCH, "--branch"),
    interval: int = typer.Option(
        DEFAULT_INTERVAL_SECONDS, "--interval", help="Seconds between automatic rounds"
    ),
    with_credentials: bool = typer.Option(
        False, "--with-credentials", help="Carry credential ciphertext (never the master key)"
    ),
    credential_ref: str = typer.Option(
        None, "--credential-ref", help="Name of the push credential in the credential store"
    ),
) -> None:
    """Configure the remote. It is probed before being accepted."""
    body = {
        "url": url,
        "branch": branch,
        "interval_seconds": interval,
        "include_credentials": with_credentials,
        "credential_ref": credential_ref,
    }
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.put("/sync/remote", json=body)
        _cli_client.check(r, verbose=verbose)
        _print_remote(r.json())


@remote_app.command("show")
def remote_show(ctx: typer.Context) -> None:
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/sync/remote")
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
    if not payload.get("configured"):
        _console.print("no sync remote configured")
        return
    _print_remote(payload["remote"])


@remote_app.command("clear")
def remote_clear(ctx: typer.Context) -> None:
    """Forget the remote. The vault is left exactly as it is."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete("/sync/remote")
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
    _console.print("[green]cleared[/green]" if payload.get("cleared") else "nothing to clear")

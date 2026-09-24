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

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import sync_join
from coffer.surfaces.cli.sync_machine_cmd import key_app, machine_app
from coffer.surfaces.cli.sync_remote_cmd import print_remote, remote_app

app = typer.Typer(help="Keep this vault converged with a git remote you own")
app.add_typer(remote_app, name="remote")
app.add_typer(machine_app, name="machine")
app.add_typer(key_app, name="key")

_console = Console()

#: Statuses that mean the user has something to do.
_NEEDS_ATTENTION = frozenset(
    {"conflict", "awaiting_confirmation", "push_failed", "failed", "awaiting_join"}
)

_NOT_JOINED = (
    "  this machine has not joined this remote yet — run 'coffer sync adopt' "
    "to see what joining would do, and join"
)


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def _counts(label: str, counts: dict[str, Any]) -> str:
    parts = [f"{k} {v}" for k, v in counts.items() if v]
    return f"{label}: {', '.join(parts)}" if parts else f"{label}: nothing"


def _print_round(run: dict[str, Any], *, joined: bool = True) -> None:
    """One round. ``joined`` is False on a machine that has not joined yet,
    where the next step is ``adopt`` rather than another ordinary round."""
    status = run.get("status", "?")
    style = "yellow" if status in _NEEDS_ATTENTION else "green"
    _console.print(f"[{style}]{status}[/{style}]")

    if status == "awaiting_join":
        # Detected on this round and deliberately not applied.
        if run.get("join_report"):
            sync_join.print_join_preview(_console, run["join_report"], lead="  Would join")
        _console.print(_NOT_JOINED)
        return
    if run.get("join"):
        kind = run["join"]
        _console.print(
            f"  joined this remote as a [bold]{kind}[/bold] machine"
            + (
                "  (its id was already in the registry, so its base came from its own descriptor)"
                if kind == "returning"
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
        then = "coffer sync now" if joined else "coffer sync adopt"
        _console.print(f"  resolve them with your own git tools, then run '{then}'")
    for failure in run.get("failures") or []:
        _console.print(f"  [red]could not apply[/red] {failure['path']}: {failure['reason']}")
    for path in run.get("not_applicable") or []:
        _console.print(f"  [dim]not applicable here[/dim]: {path}")
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
    yes: bool = typer.Option(False, "--yes", help="Join without asking, after the report"),
) -> None:
    """Join the remote. A new machine takes the union; a returning one recovers its base.

    States the case and the counts first and asks before anything is applied.
    """
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        if url:
            r = c.put("/sync/remote", json={"url": url})
            _cli_client.check(r, verbose=verbose)
        body = {"choice": "keep-local"} if keep_local else {}
        r = c.get("/sync/join", params=body)
        _cli_client.check(r, verbose=verbose)
        if (preview := r.json()).get("joining"):
            sync_join.print_join_preview(_console, preview)
            sync_join.confirm_join(_console, preview, yes=yes)
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
    """What the remote is, and how the last round went.

    Exits **non-zero** when the last round needs a human — held for
    confirmation, conflicted, or failed to push or run at all — so that a
    prompt, a cron line or a monitor can notice without reading the text. A
    vault held on a confirmation nobody sees converges no further, and the
    first time that happened in the field it went unnoticed for four days
    (spec vault-sync "Say a vault needs a human where the user already is").
    """
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/sync/status")
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
    if not payload.get("configured"):
        _console.print("no sync remote configured — 'coffer sync remote set <url>'")
    else:
        print_remote(payload["remote"])
    _console.print(f"this machine: {payload.get('machine_id')}")
    if not payload.get("machine_id_is_derived"):
        _console.print(
            "  [yellow]note[/yellow]: this id is stored locally, not derived from the host, "
            "so deleting ~/.coffer makes this machine reappear as a new one"
        )
    last = payload.get("last_run")
    # A recorded awaiting_join round says this itself, below.
    waiting = (last or {}).get("status") == "awaiting_join"
    if payload.get("configured") and not payload.get("joined") and not waiting:
        _console.print(_NOT_JOINED.strip())
    for path in payload.get("not_applicable") or []:
        _console.print(f"not applicable here: {path}")
    if last is None:
        _console.print("no round yet")
        return
    _print_round(last, joined=bool(payload.get("joined", True)))
    # Only while sync is actually on. A disabled remote makes a round return
    # DISABLED without recording it, so ``last_run`` keeps whatever it last
    # was; exiting non-zero on that would leave a vault whose sync the user
    # deliberately switched off failing every check that asks, for ever.
    remote = payload.get("remote") or {}
    if remote.get("enabled") and last.get("status") in _NEEDS_ATTENTION:
        raise typer.Exit(code=1)


@app.command("history")
def history(
    ctx: typer.Context,
    limit: int = typer.Option(20, "--limit", help="How many rounds to show, newest first"),
) -> None:
    """Every round this machine has run, newest first.

    One line each rather than the full report ``status`` prints: what this
    answers is the shape of the sequence — whether rounds are still happening,
    when they stopped, which one moved a lot of documents.
    """
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/sync/runs", params={"limit": limit})
        _cli_client.check(r, verbose=verbose)
        runs = r.json().get("runs") or []
    if not runs:
        _console.print("no round yet")
        return
    for run in runs:
        status = run.get("status", "?")
        style = "yellow" if status in _NEEDS_ATTENTION else "green"
        commit = (run.get("commit") or "")[:12] or "—"
        _console.print(
            f"{run.get('finished_at', '?')}  [{style}]{status}[/{style}]  "
            + _counts("applied", run.get("applied") or {})
            + "  "
            + _counts("published", run.get("published") or {})
            + f"  {commit}"
        )

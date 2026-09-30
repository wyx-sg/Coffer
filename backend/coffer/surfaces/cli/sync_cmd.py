"""``coffer sync ...`` (spec vault-sync; ADR
sync-applies-clean-merges-and-stops-on-any-conflict).

Sync only pulls and pushes the vault repository: a merge git completes
cleanly is applied, and any conflict stops the round for the person. These
commands run a round, show what it did, and answer what it stopped on; the
remote, the machines and the master key have their own groups.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import sync_stop_cmd
from coffer.surfaces.cli.sync_machine_cmd import key_app, machine_app
from coffer.surfaces.cli.sync_print import NEEDS_PERSON, changes, print_round, verbose_of
from coffer.surfaces.cli.sync_remote_cmd import print_remote, remote_app

app = typer.Typer(help="Keep this vault in step with a git remote you own")
app.add_typer(remote_app, name="remote")
app.add_typer(machine_app, name="machine")
app.add_typer(key_app, name="key")

_console = Console()


@app.command("now")
def sync_now(ctx: typer.Context) -> None:
    """Run one round with the remote, right now."""
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/run", json={})
        _cli_client.check(r, verbose=verbose)
        print_round(r.json())


@app.command("status")
def status(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """The remote, the last round, and anything waiting for you.

    Exits 1 while a round waits for a person — stopped on conflicts, held,
    unable to reach or sign in to the remote, or paused because the vault is
    inside a synchronised folder — so a prompt or a monitor notices without
    reading the text. A paused remote exits 0.

    \f
    Spec vault-sync "Say a vault needs a human where the user already is".
    """
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/sync/status")
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
    if output_json:
        typer.echo(_json.dumps(payload, indent=2))
    else:
        _print_status(payload)
    remote = payload.get("remote") or {}
    last = payload.get("last_round") or {}
    waiting = payload.get("conflicts") or payload.get("held") or payload.get("join_choices")
    if remote.get("enabled") and (waiting or last.get("status") in NEEDS_PERSON):
        raise typer.Exit(code=1)


def _print_status(payload: dict[str, Any]) -> None:
    if not payload.get("configured"):
        _console.print("no sync remote configured — set one with: coffer sync remote set <url>")
    else:
        print_remote(payload["remote"])
    _console.print(f"this machine: {payload.get('machine_name')} ({payload.get('machine_id')})")
    _console.print(f"vault: {payload.get('vault_path')}")
    if payload.get("synchroniser"):
        _console.print(
            f"  [red]unsupported[/red]: the vault is inside a folder "
            f"{payload['synchroniser']} synchronises; sync is paused until it moves"
        )
    areas = payload.get("areas") or {}
    secrets = "synced" if areas.get("secrets_synced") else "not synced"
    _console.print(
        f"  {areas.get('knowledge_documents', 0)} knowledge documents · "
        f"{areas.get('skills', 0)} skills · {areas.get('resources', 0)} resource definitions · "
        f"{areas.get('secrets', 0)} encrypted secrets ({secrets})"
    )
    if payload.get("configured") and not payload.get("joined"):
        _console.print("  not joined yet: 'coffer sync join' shows what joining would do")
    waiting = payload.get("waiting") or []
    if waiting:
        files = sum(len(w.get("changes") or []) for w in waiting)
        _console.print(f"  {files} change(s) in {len(waiting)} commit(s) waiting to push")
    for key, text in (
        ("conflicts", "file(s) to resolve: coffer sync conflicts"),
        ("held", "file(s) held: coffer sync hold"),
        ("join_choices", "file(s) differ from the remote: coffer sync choose"),
    ):
        if payload.get(key):
            _console.print(f"  [yellow]{payload[key]} {text}[/yellow]")
    problem = payload.get("problem")
    if problem:
        ref = f" (token {problem['secret_ref']})" if problem.get("secret_ref") else ""
        _console.print(f"  [red]{problem['kind']}[/red]{ref}: {problem['message']}")
    if payload.get("next_round_at"):
        _console.print(f"  next round: {payload['next_round_at']}")
    last = payload.get("last_round")
    if last:
        _console.print(f"last round, {last.get('finished_at')}:")
        print_round(last, detail=False)
    else:
        _console.print("no round yet")


@app.command("history")
def history(
    ctx: typer.Context,
    limit: int = typer.Option(20, "--limit", help="How many rounds to show, newest first"),
) -> None:
    """Every round this machine has run, newest first, one line each."""
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/sync/runs", params={"limit": limit})
        _cli_client.check(r, verbose=verbose)
        rounds = r.json().get("rounds") or []
    if not rounds:
        _console.print("no round yet")
        return
    for run in rounds:
        status_ = run.get("status", "?")
        style = "yellow" if status_ in NEEDS_PERSON else "green"
        _console.print(
            f"{run.get('id'):>5}  {run.get('finished_at', '?')}  [{style}]{status_}[/{style}]  "
            + changes("pulled", run.get("applied") or [])
            + "  "
            + changes("pushed", run.get("pushed") or [])
        )


@app.command("rollback")
def rollback(
    ctx: typer.Context,
    run_id: int = typer.Argument(..., help="The round to roll back (see coffer sync history)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask before rolling back"),
) -> None:
    """Put back what one round changed, from its snapshot.

    The plan is printed first. Rolling back is a new commit on this machine,
    which the next round pushes; files edited since the round are kept.

    \f
    Spec vault-sync "Snapshot before checking out and roll a round back from it".
    """
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/sync/runs/{run_id}/rollback-plan")
        _cli_client.check(r, verbose=verbose)
        plan = r.json()
        _console.print(f"back to snapshot {plan['snapshot']} ({plan.get('snapshot_time') or '?'}):")
        for change in plan.get("reverses") or []:
            _console.print(f"  {change['status']:<8} {change['path']}")
        for path in plan.get("kept") or []:
            _console.print(f"  kept     {path}  (edited since)")
        if not yes and not typer.confirm("Roll back?", default=False):
            raise typer.Exit(code=1)
        r = c.post(f"/sync/runs/{run_id}/rollback", json={})
        _cli_client.check(r, verbose=verbose)
        print_round(r.json())


sync_stop_cmd.register(app)

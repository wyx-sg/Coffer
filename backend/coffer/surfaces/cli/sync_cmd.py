"""coffer sync ... commands (spec 010 multi-machine sync)."""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(
    help="Sync the vault across your machines via a git repo you own",
    invoke_without_command=True,
)
key_app = typer.Typer(help="Out-of-band master-key transfer for new machines")
app.add_typer(key_app, name="key")
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _print_status(payload: dict[str, Any]) -> None:
    status = payload["status"]
    _console.print(f"sync status: [bold]{status}[/bold]")
    if payload.get("last_sync_at"):
        _console.print(f"  last sync: {payload['last_sync_at']}")
    if payload.get("conflict_paths"):
        _console.print("  conflicts:")
        for p in payload["conflict_paths"]:
            _console.print(f"    - {p}")
    if payload.get("locked_refs"):
        _console.print(f"  locked credentials: {', '.join(payload['locked_refs'])}")
        _console.print("  (run 'coffer sync key import <path>' to unlock)")
    if payload.get("last_error"):
        _console.print(f"  [red]error:[/red] {payload['last_error']}")


def _run(verbose: bool, *, pull: bool = True, push: bool = True) -> None:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/run", json={"pull": pull, "push": push})
        _cli_client.check(r, verbose=verbose)
    _print_status(r.json())


@app.callback()
def _default(ctx: typer.Context) -> None:
    """Running `coffer sync` with no subcommand performs a full sync."""
    if ctx.invoked_subcommand is None:
        _run(_verbose(ctx))


@app.command()
def init(
    ctx: typer.Context,
    remote: str = typer.Argument(..., help="Git remote URL you own"),
    branch: str = typer.Option("main", "--branch", help="Branch to sync on"),
) -> None:
    """Point sync at a remote, enable it, and do a first sync run."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.put(
            "/sync/config",
            json={
                "remote": remote,
                "enabled": True,
                "auto": False,
                "interval_seconds": 300,
                "branch": branch,
            },
        )
        _cli_client.check(r, verbose=verbose)
    _run(verbose)


@app.command()
def run(
    ctx: typer.Context,
    no_pull: bool = typer.Option(False, "--no-pull", help="Skip the pull/merge step"),
    no_push: bool = typer.Option(False, "--no-push", help="Skip pushing after merge"),
) -> None:
    """Run a full sync: export -> pull -> push -> import."""
    _run(_verbose(ctx), pull=not no_pull, push=not no_push)


@app.command()
def push(ctx: typer.Context) -> None:
    """Export and push local changes (no import)."""
    _run(_verbose(ctx), pull=False)


@app.command()
def pull(ctx: typer.Context) -> None:
    """Pull and import remote changes (no push)."""
    _run(_verbose(ctx), push=False)


@app.command()
def status(ctx: typer.Context) -> None:
    """Show the last sync status."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/sync/status")
        _cli_client.check(r, verbose=verbose)
    _print_status(r.json())


@app.command()
def config(
    ctx: typer.Context,
    auto: str | None = typer.Option(None, "--auto", help="on | off — enable auto-sync"),
    interval: int | None = typer.Option(None, "--interval", help="Auto-sync interval (seconds)"),
    remote: str | None = typer.Option(None, "--remote", help="Change the git remote"),
    branch: str | None = typer.Option(None, "--branch", help="Change the branch"),
    enable: bool = typer.Option(False, "--enable", help="Enable sync"),
    disable: bool = typer.Option(False, "--disable", help="Disable sync"),
) -> None:
    """Show or change sync configuration."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        current = c.get("/sync/config")
        _cli_client.check(current, verbose=verbose)
        cfg = current.json()
        if any(v is not None for v in (auto, interval, remote, branch)) or enable or disable:
            if auto is not None:
                cfg["auto"] = auto.lower() in ("on", "true", "yes", "1")
            if interval is not None:
                cfg["interval_seconds"] = interval
            if remote is not None:
                cfg["remote"] = remote
            if branch is not None:
                cfg["branch"] = branch
            if enable:
                cfg["enabled"] = True
            if disable:
                cfg["enabled"] = False
            r = c.put("/sync/config", json=cfg)
            _cli_client.check(r, verbose=verbose)
            cfg = r.json()
    typer.echo(_json.dumps(cfg, indent=2))


@app.command()
def resolve(
    ctx: typer.Context,
    ours: bool = typer.Option(False, "--ours", help="Keep this machine's version"),
    theirs: bool = typer.Option(False, "--theirs", help="Keep the remote version"),
    resolved: bool = typer.Option(False, "--resolved", help="Mark hand-edited paths resolved"),
    paths: list[str] = typer.Argument(  # noqa: B008 — typer argument declaration
        None, help="Paths to resolve (default: all)"
    ),
) -> None:
    """Resolve sync conflicts, then finish the run."""
    verbose = _verbose(ctx)
    chosen = [n for n, on in (("ours", ours), ("theirs", theirs), ("resolved", resolved)) if on]
    if len(chosen) != 1:
        typer.echo("pick exactly one of --ours / --theirs / --resolved", err=True)
        raise typer.Exit(2)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/resolve", json={"strategy": chosen[0], "paths": paths or []})
        _cli_client.check(r, verbose=verbose)
    _print_status(r.json())


@key_app.command("export")
def key_export(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Local file to write the master key to"),
) -> None:
    """Export this machine's master key to a file (move it out-of-band)."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/key/export", json={"path": path})
        _cli_client.check(r, verbose=verbose)
    _console.print(f"master key written to {r.json()['path']}")
    _console.print("[yellow]move it over a channel you trust — never via the sync repo[/yellow]")


@key_app.command("import")
def key_import(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Local file holding a master key from another machine"),
) -> None:
    """Install a master key brought from another machine, unlocking credentials."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/key/import", json={"path": path})
        _cli_client.check(r, verbose=verbose)
    _print_status(r.json())

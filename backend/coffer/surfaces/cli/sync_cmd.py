"""coffer sync ... commands (spec vault-export-import vault export/import).

Two halves. ``export``/``import``/``key`` move a vault by hand. ``remote``,
``push``, ``restore`` and ``status`` drive the one git remote exports are
backed up to (spec ``## Backup``) — always through the daemon, which owns the
git working tree and is the only thing that ever resolves the push credential.

Nothing here restores on its own: ``restore`` overwrites local state, so it is
only ever the command the user typed (spec ``### Restore``).
"""

from __future__ import annotations

import pathlib
from typing import Any

import typer
from rich.console import Console

from coffer.domain.sync.backup import DEFAULT_BRANCH, DEFAULT_INTERVAL_SECONDS
from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Export this vault, import one back, or back it up to a git remote")
key_app = typer.Typer(help="Out-of-band master-key transfer for new machines")
app.add_typer(key_app, name="key")
remote_app = typer.Typer(help="The one git remote this vault is backed up to")
app.add_typer(remote_app, name="remote")
_console = Console()

#: What a bundle holds, in the order the exporter writes it. Shown when a
#: remote is configured because a URL on its own tells the user nothing about
#: what they just agreed to put on someone else's disk.
_BUNDLE_AREAS: tuple[tuple[str, str], ...] = (
    ("knowledge", "every document under ~/.coffer/knowledge"),
    ("skills", "the master skill store"),
    ("resources", "mcp_server, agent, skill and channel definitions"),
    ("state", "shared state: pairings, scope labels, plugin inventory"),
)

#: Run statuses that mean the remote does not yet hold this vault.
_FAILED_STATUSES = frozenset({"push_failed", "export_failed"})


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _print_summary(payload: dict[str, Any]) -> None:
    """Counts per area, the resources that failed, and the bundle path."""
    _console.print(f"bundle: [bold]{payload['path']}[/bold]")
    areas = payload.get("areas") or []
    if areas:
        for area in areas:
            _console.print(f"  {area['area']}: {area['count']}")
    else:
        _console.print("  (nothing to report)")
    for ref, reason in (tuple(f) for f in payload.get("failures") or []):
        _console.print(f"  [red]failed[/red] {ref}: {reason}")
    if payload.get("locked_refs"):
        _console.print(f"  locked credentials: {', '.join(payload['locked_refs'])}")
        _console.print("  (run 'coffer sync key import <path>' to unlock)")


@app.command("export")
def export_bundle(
    ctx: typer.Context,
    directory: str = typer.Argument(..., help="Directory to write the export bundle into"),
    with_credentials: bool = typer.Option(
        False,
        "--with-credentials",
        help="Include credential ciphertext (never the master key)",
    ),
) -> None:
    """Export this vault into a directory you can carry to another machine."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            "/sync/export",
            json={"path": directory, "with_credentials": with_credentials},
        )
        _cli_client.check(r, verbose=verbose)
    _print_summary(r.json())
    if with_credentials:
        _console.print(
            "[yellow]this bundle holds credential ciphertext — move it somewhere you trust[/yellow]"
        )


@app.command("import")
def import_bundle(
    ctx: typer.Context,
    directory: str = typer.Argument(..., help="Export bundle directory to import"),
) -> None:
    """Import an export bundle into this vault (never deletes local-only items)."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/import", json={"path": directory})
        _cli_client.check(r, verbose=verbose)
    _print_summary(r.json())


@key_app.command("export")
def key_export(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Local file to write the master key to"),
) -> None:
    """Export this machine's master key to a file (move it out-of-band)."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/key/export", json={})
        _cli_client.check(r, verbose=verbose)
    # The daemon hands back the material; the CLI writes the file, so the
    # daemon never opens a path a caller named.
    target = pathlib.Path(path).expanduser()
    target.write_text(r.json()["material"], encoding="utf-8")
    target.chmod(0o600)
    _console.print(f"master key written to {target}")
    _console.print("[yellow]move it over a channel you trust — never inside a bundle[/yellow]")


@key_app.command("import")
def key_import(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Local file holding a master key from another machine"),
) -> None:
    """Install a master key brought from another machine, unlocking credentials."""
    verbose = _verbose(ctx)
    source = pathlib.Path(path).expanduser()
    if not source.exists():
        _console.print(f"[red]no such file: {source}[/red]")
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/key/import", json={"material": source.read_text(encoding="utf-8")})
        _cli_client.check(r, verbose=verbose)
    locked = r.json()["locked_refs"]
    if locked:
        _console.print(f"key installed; still locked: {', '.join(locked)}")
    else:
        _console.print("key installed; all credentials unlock on this machine")


# --- backup (spec vault-export-import ``## Backup``) ------------------------


def _print_remote(remote: dict[str, Any]) -> None:
    """Render the configured remote.

    ``push credential`` is the *reference* the daemon resolves at push time —
    a name in the credential store. The secret itself never crosses the API,
    so there is nothing here to redact.
    """
    _console.print(f"remote: [bold]{remote['url']}[/bold]")
    _console.print(f"  branch: {remote['branch']}")
    _console.print(f"  interval: {remote['interval_seconds']}s")
    _console.print(f"  worktree: {remote['worktree_path']}")
    _console.print(f"  enabled: {'yes' if remote['enabled'] else 'no'}")
    _console.print(f"  push credential: {remote['credential_ref'] or '(none)'}")


def _print_push_contents(*, with_credentials: bool) -> None:
    """Say what a push will put on the remote, area by area."""
    _console.print("a push will contain:")
    for area, what in _BUNDLE_AREAS:
        _console.print(f"  {area}: {what}")
    if with_credentials:
        _console.print("  credentials: Fernet ciphertext (never the master key)")
        _console.print(
            "[yellow]credential ciphertext rides along — push only to a repository you own[/yellow]"
        )
    else:
        _console.print("  credentials: not included")


def _print_run(run: dict[str, Any] | None) -> None:
    """Render one backup run, or say that none has happened yet."""
    if run is None:
        _console.print("last run: (none yet)")
        return
    status = run["status"]
    colour = "red" if status in _FAILED_STATUSES else "green"
    _console.print(f"last run: [{colour}]{status}[/{colour}]")
    if run.get("ran_at"):
        _console.print(f"  at: {run['ran_at']}")
    if run.get("commit"):
        _console.print(f"  commit: {run['commit']}")
    if run.get("error"):
        _console.print(f"  [red]error[/red]: {run['error']}")


@remote_app.command("set")
def remote_set(
    ctx: typer.Context,
    url: str = typer.Argument(..., help="Git URL of a repository you own"),
    branch: str = typer.Option(DEFAULT_BRANCH, "--branch", help="Branch to push to"),
    interval: int = typer.Option(
        DEFAULT_INTERVAL_SECONDS, "--interval", help="Seconds between automatic backups"
    ),
    with_credentials: bool = typer.Option(
        False,
        "--with-credentials",
        help="Every backup carries credential ciphertext (stored, not per-run)",
    ),
    credential_ref: str | None = typer.Option(
        None,
        "--credential-ref",
        help=(
            "Credential store reference holding the push token, "
            "e.g. sync.BACKUP_TOKEN (store it first with 'coffer credentials set')"
        ),
    ),
) -> None:
    """Configure the one backup remote, and say what a push will contain."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        # `set` names a remote; it is not a way to forget a push credential
        # configured elsewhere, so an existing ref is carried forward unless
        # this call names one.
        current = c.get("/sync/remote")
        _cli_client.check(current, verbose=verbose)
        existing = current.json().get("remote") or {}
        if credential_ref is not None:
            existing = {**existing, "credential_ref": credential_ref.strip() or None}
        r = c.put(
            "/sync/remote",
            json={
                "url": url,
                "branch": branch,
                "interval_seconds": interval,
                "include_credentials": with_credentials,
                "credential_ref": existing.get("credential_ref"),
                "enabled": True,
            },
        )
        _cli_client.check(r, verbose=verbose)
    _print_remote(r.json())
    _print_push_contents(with_credentials=with_credentials)


@remote_app.command("show")
def remote_show(ctx: typer.Context) -> None:
    """Show the configured backup remote (its credential ref, never a secret)."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/sync/remote")
        _cli_client.check(r, verbose=verbose)
    payload = r.json()
    if not payload["configured"]:
        _console.print("no backup remote configured")
        _console.print("  (run 'coffer sync remote set <url>' to configure one)")
        return
    remote = payload["remote"]
    _print_remote(remote)
    _print_push_contents(with_credentials=remote["include_credentials"])


@remote_app.command("clear")
def remote_clear(ctx: typer.Context) -> None:
    """Turn backup off. The working tree and its history are left alone."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete("/sync/remote")
        _cli_client.check(r, verbose=verbose)
    if r.json()["cleared"]:
        _console.print("backup remote cleared; the local working tree is untouched")
    else:
        _console.print("no backup remote was configured")


@app.command("push")
def push(ctx: typer.Context) -> None:
    """Back the vault up now: export, commit if it changed, push."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/push", json={})
        _cli_client.check(r, verbose=verbose)
    run = r.json()
    _print_run(run)
    if run["status"] in _FAILED_STATUSES:
        # The commit, if one was made, is still there — but this shell (or the
        # script that called it) should hear that the remote is not current.
        raise typer.Exit(1)


@app.command("restore")
def restore(
    ctx: typer.Context,
    at: str | None = typer.Option(
        None,
        "--at",
        help="Revision, ref, or YYYY-MM-DD date — the last commit at or before it",
    ),
    from_url: str | None = typer.Option(
        None,
        "--from",
        help="Clone from this URL when this machine has no working tree yet",
    ),
) -> None:
    """Import the backup into this vault (never automatic, never deletes).

    Without ``--at`` this restores the remote's tip, which mirrors deletions as
    faithfully as additions — so recovering something deleted last week means
    naming a revision or a date.
    """
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/restore", json={"at": at, "from_url": from_url})
        _cli_client.check(r, verbose=verbose)
    _print_summary(r.json())


@app.command("status")
def status(ctx: typer.Context) -> None:
    """Report the backup remote and what its last run did."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/sync/status")
        _cli_client.check(r, verbose=verbose)
    payload = r.json()
    if not payload["configured"]:
        _console.print("no backup remote configured")
        _console.print("  (run 'coffer sync remote set <url>' to configure one)")
        return
    _print_remote(payload["remote"])
    _print_run(payload["last_run"])

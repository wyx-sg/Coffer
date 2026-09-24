"""``coffer sync remote ...`` (spec vault-sync).

Split out of ``sync_cmd.py`` for the file-size tier. Re-running ``remote set``
changes what it names and nothing else (spec vault-sync "Pause a configured
remote without forgetting it"), so every option defaults to "keep what is
stored" and the stored remote is the base the request is built on.
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console

from coffer.domain.sync.backup import DEFAULT_BRANCH, DEFAULT_INTERVAL_SECONDS
from coffer.surfaces.cli import _client as _cli_client

remote_app = typer.Typer(help="The one git remote this vault converges with")

_console = Console()

#: What a remote configured for the first time takes for an option not given.
#: ``worktree_path`` is absent: the daemon's own default applies.
_FIRST_TIME: dict[str, Any] = {
    "branch": DEFAULT_BRANCH,
    "interval_seconds": DEFAULT_INTERVAL_SECONDS,
    "include_credentials": False,
    "credential_ref": None,
    "enabled": True,
}


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def remote_body(current: dict[str, Any] | None, url: str, **given: Any) -> dict[str, Any]:
    """The ``PUT /sync/remote`` body: the stored remote (or the first-time
    defaults), with ``url`` and every option the user passed laid over it.

    An option left at ``None`` was not passed and keeps its stored value; an
    empty ``credential_ref`` is the one way to say "no push credential"."""
    body = dict(current) if current else dict(_FIRST_TIME)
    body.update({k: v for k, v in given.items() if v is not None})
    if body.get("credential_ref") == "":
        body["credential_ref"] = None
    body["url"] = url
    return body


def print_remote(remote: dict[str, Any]) -> None:
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
    branch: str | None = typer.Option(None, "--branch", help=f"Default {DEFAULT_BRANCH}"),
    interval: int | None = typer.Option(
        None,
        "--interval",
        help=f"Seconds between automatic rounds (default {DEFAULT_INTERVAL_SECONDS})",
    ),
    with_credentials: bool | None = typer.Option(
        None,
        "--with-credentials/--without-credentials",
        help="Carry credential ciphertext (never the master key); default off",
    ),
    credential_ref: str | None = typer.Option(
        None,
        "--credential-ref",
        help="Name of the push credential in the credential store ('' removes it)",
    ),
    worktree: str | None = typer.Option(
        None,
        "--worktree",
        help="Absolute path of the git working tree, outside the vault (default ~/.coffer/sync)",
    ),
) -> None:
    """Configure the remote. It is probed before being accepted.

    On a configured remote an option not given keeps its stored value, and
    ``enabled`` is never changed here: re-running never unpauses. A remote set
    for the first time takes the defaults and starts enabled. A working tree
    at, inside or above the vault is refused by the daemon with its reason
    (spec vault-sync "Keep the working tree outside the vault")."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        current = c.get("/sync/remote")
        _cli_client.check(current, verbose=verbose)
        body = remote_body(
            current.json().get("remote"),
            url,
            branch=branch,
            interval_seconds=interval,
            include_credentials=with_credentials,
            credential_ref=credential_ref,
            worktree_path=worktree,
        )
        r = c.put("/sync/remote", json=body)
        _cli_client.check(r, verbose=verbose)
        print_remote(r.json())


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
    print_remote(payload["remote"])


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

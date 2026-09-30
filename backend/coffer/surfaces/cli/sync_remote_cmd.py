"""``coffer sync remote ...`` (spec vault-sync "Allow at most one user-owned
sync remote").

Split out of ``sync_cmd.py`` for the file-size tier. Re-running ``remote set``
changes what it names and nothing else, so every option defaults to "keep
what is stored" and the stored remote is the base the request is built on.
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console

from coffer.domain.sync.remote import DEFAULT_BRANCH, DEFAULT_INTERVAL_SECONDS, DEFAULT_USERNAME
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._approvals import WAIT_OPTION, pending_ids, settle_ids
from coffer.surfaces.cli._options import ExitCode

remote_app = typer.Typer(help="The one git remote this vault syncs with")

_console = Console()

#: What a remote configured for the first time takes for an option not given.
_FIRST_TIME: dict[str, Any] = {
    "branch": DEFAULT_BRANCH,
    "interval_seconds": DEFAULT_INTERVAL_SECONDS,
    "include_secret": False,
    "secret_ref": None,
    "username": DEFAULT_USERNAME,
    "enabled": True,
}


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def remote_body(current: dict[str, Any] | None, url: str, **given: Any) -> dict[str, Any]:
    """The ``PUT /sync/remote`` body: the stored remote (or the first-time
    defaults), with ``url`` and every option the user passed laid over it.

    An option left at ``None`` was not passed and keeps its stored value; an
    empty ``secret_ref`` is the one way to say "no push secret"."""
    body = dict(current) if current else dict(_FIRST_TIME)
    body.update({k: v for k, v in given.items() if v is not None})
    if body.get("secret_ref") == "":
        body["secret_ref"] = None
    body["url"] = url
    return body


def print_remote(remote: dict[str, Any]) -> None:
    """Every setting of the stored remote — what ``coffer sync status`` and
    ``remote set|pause|resume`` print."""
    _console.print(f"remote: {remote['url']}  branch {remote['branch']}")
    _console.print(
        f"  every {remote['interval_seconds']}s · "
        f"encrypted secrets {'included' if remote['include_secret'] else 'not synced'} · "
        f"{'enabled' if remote['enabled'] else 'paused'}"
    )
    _console.print(
        f"  push token: {remote.get('secret_ref') or '(none)'}"
        f" · username {remote.get('username') or DEFAULT_USERNAME}"
    )


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
    with_secret: bool | None = typer.Option(
        None,
        "--with-secret/--without-secret",
        help="Carry the encrypted secrets (ciphertext, never the master key); default off",
    ),
    secret_ref: str | None = typer.Option(
        None,
        "--secret-ref",
        help="Name of the push token in the secret store ('' removes it)",
    ),
    username: str | None = typer.Option(
        None,
        "--username",
        help=f"Username sent with an HTTPS token (default {DEFAULT_USERNAME}; "
        "Bitbucket and Azure DevOps need a real one)",
    ),
    wait: bool = WAIT_OPTION,
) -> None:
    """Configure the remote ('coffer sync remote check' looks at it first).

    On a configured remote an option not given keeps its stored value, and a
    paused remote stays paused (`coffer sync remote resume` resumes it). A
    remote set for the first time takes the defaults and starts enabled."""
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
            include_secret=with_secret,
            secret_ref=secret_ref,
            username=username,
        )
        r = c.put("/sync/remote", json=body)
        # An existing push token pointed at a new URL is the token going
        # somewhere new: nothing is saved until the Coffer app approves it.
        waiting = pending_ids(r)
        if waiting:
            settle_ids(c, waiting, wait=wait, verbose=verbose)
            r = c.put("/sync/remote", json=body)
        _cli_client.check(r, verbose=verbose)
        print_remote(r.json())


@remote_app.command("clear")
def remote_clear(ctx: typer.Context) -> None:
    """Stop syncing: forget the remote. The vault is left exactly as it is."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete("/sync/remote")
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
    _console.print("[green]cleared[/green]" if payload.get("cleared") else "nothing to clear")


def _switch(ctx: typer.Context, *, enabled: bool) -> None:
    """Flip the stored remote's ``enabled`` and nothing else — the same
    ``PUT /sync/remote`` the web UI's switch sends, built on what is stored."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        current = c.get("/sync/remote")
        _cli_client.check(current, verbose=verbose)
        payload = current.json()
        if not payload.get("configured"):
            typer.echo(
                "no sync remote configured — set one with: coffer sync remote set <url>", err=True
            )
            raise typer.Exit(int(ExitCode.NOT_FOUND))
        r = c.put("/sync/remote", json={**payload["remote"], "enabled": enabled})
        _cli_client.check(r, verbose=verbose)
        print_remote(r.json())


@remote_app.command("pause")
def remote_pause(ctx: typer.Context) -> None:
    """Pause sync. The remote, its settings and the history are all kept."""
    _switch(ctx, enabled=False)


@remote_app.command("resume")
def remote_resume(ctx: typer.Context) -> None:
    """Resume a paused remote where the vault left off."""
    _switch(ctx, enabled=True)


@remote_app.command("check")
def remote_check(
    ctx: typer.Context,
    url: str | None = typer.Argument(None, help="A remote to look at (default: the stored one)"),
    branch: str | None = typer.Option(None, "--branch", help=f"Default {DEFAULT_BRANCH}"),
    secret_ref: str | None = typer.Option(None, "--secret-ref", help="Push token to use"),
) -> None:
    """Look at a remote without keeping it: empty, a Coffer vault (and its
    layout), another repository, unreachable, or refusing the token."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        stored = c.get("/sync/remote")
        _cli_client.check(stored, verbose=verbose)
        current = stored.json().get("remote") or {}
        target = url or current.get("url")
        if not target:
            typer.echo("no remote given or stored", err=True)
            raise typer.Exit(int(ExitCode.NOT_FOUND))
        body = {
            "url": target,
            "branch": branch or current.get("branch") or DEFAULT_BRANCH,
            "secret_ref": secret_ref if secret_ref is not None else current.get("secret_ref"),
        }
        r = c.post("/sync/remote/check", json=body)
        _cli_client.check(r, verbose=verbose)
        found = r.json()
    result = found["result"]
    words = {
        "empty": "empty — the first round pushes this vault",
        "vault": f"a Coffer vault (layout {found.get('layout')})",
        "other": "a repository that is not a Coffer vault",
    }
    style = "green" if result in words else "red"
    _console.print(f"[{style}]{words.get(result, result)}[/{style}]")
    if found.get("detail"):
        _console.print(f"  {found['detail']}")
    if result not in words:
        raise typer.Exit(code=1)

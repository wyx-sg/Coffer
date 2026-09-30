"""``coffer sync join|conflicts|resolve|edit|continue|hold|choose``: answering
what a round stopped on (spec vault-sync "Report a join before applying it",
"Hold a round that would lose too much").

A stopped round is answered file by file — keep this machine's version, take
the other machine's, or hand-merge a marked-up copy — and nothing is written
into the vault until ``continue``. Registered on ``coffer sync`` by
``sync_cmd`` (split for the file-size tier).
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli.sync_print import print_round

_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def _areas(items: list[dict[str, Any]]) -> str:
    return ", ".join(f"{a['files']} {a['area']}" for a in items) or "nothing"


def print_preview(p: dict[str, Any]) -> None:
    if p.get("refused"):
        _console.print(f"[red]cannot join[/red]: {p['refused']}")
        return
    kind = p.get("kind")
    if kind == "empty":
        _console.print("the remote is empty: joining pushes this whole vault")
        _console.print(f"  pushed: {_areas(p.get('pushed') or [])}")
        return
    who = f" (last pushed by {p['pushed_by']}, {p.get('pushed_at')})" if p.get("pushed_by") else ""
    _console.print(f"joining as a [bold]{kind}[/bold] machine{who}")
    _console.print(f"  pulled: {_areas(p.get('pulled') or [])}")
    _console.print(f"  pushed: {_areas(p.get('pushed') or [])}")
    if kind == "new":
        _console.print(f"  the same on both: {p.get('same', 0)} file(s); nothing is deleted")
        for path in p.get("differ") or []:
            _console.print(f"  differs, left as it is here until you choose: {path}")
    for path in p.get("deleted") or []:
        _console.print(f"  deleted: {path}")
    for path in (p.get("conflicts") or []) + (p.get("same_name") or []):
        _console.print(f"  [yellow]to resolve[/yellow]: {path}")


def _answer(choice_mine: bool, choice_theirs: bool, choice_edited: bool = False) -> str:
    chosen = [
        n
        for n, on in (("mine", choice_mine), ("theirs", choice_theirs), ("edited", choice_edited))
        if on
    ]
    if len(chosen) != 1:
        typer.echo("choose exactly one of the answers", err=True)
        raise typer.Exit(int(ExitCode.INVALID_USAGE))
    return chosen[0]


def _print_stop(state: dict[str, Any]) -> None:
    stopped = state.get("round")
    if not state.get("stopped") or not stopped:
        _console.print("no round is waiting for you")
        return
    if stopped["kind"] == "hold":
        hold = stopped["hold"]
        where = "here" if hold["direction"] == "incoming" else "on the remote"
        by = ", ".join(hold.get("machines") or []) or "a machine"
        _console.print(
            f"[yellow]held[/yellow]: {by} would delete {len(hold['paths'])} file(s) {where}"
        )
        for group in hold.get("groups") or []:
            share = round(100 * len(group["paths"]) / group["total"]) if group["total"] else 100
            _console.print(
                f"  {group['folder']}: {len(group['paths'])} files · {share}% of the folder"
            )
            for path in group["paths"][:10]:
                _console.print(f"    - {path}")
        _console.print("  'coffer sync hold --confirm' deletes them, '--restore' keeps them")
        return
    files = stopped.get("files") or []
    _console.print(
        f"[yellow]stopped[/yellow]: {len(files) - stopped['unanswered']} of {len(files)} resolved"
    )
    for f in files:
        answer = f.get("answer") or "unresolved"
        other = f.get("theirs_machine") or "other machine"
        _console.print(
            f"  {f['path']}  [{f['area']}] {f['reason']}  this machine {f.get('ours_time') or '—'}"
            f" · {other} {f.get('theirs_time') or '—'}  → {answer}"
        )
    _console.print("  resolve each with 'coffer sync resolve PATH --mine|--theirs|--edited'")


def register(app: typer.Typer) -> None:
    @app.command("join")
    def join(
        ctx: typer.Context,
        yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask before joining"),
    ) -> None:
        """Join the configured remote. What joining would do is printed first;
        joining never deletes a file on either side."""
        verbose = _verbose(ctx)
        c, _info = _cli_client.client_or_exit()
        with c:
            r = c.get("/sync/join/preview")
            _cli_client.check(r, verbose=verbose)
            preview = r.json()
            print_preview(preview)
            if preview.get("refused"):
                raise typer.Exit(code=1)
            if not yes and not typer.confirm("Join?", default=False):
                raise typer.Exit(code=1)
            r = c.post("/sync/join", json={})
            _cli_client.check(r, verbose=verbose)
            print_round(r.json())

    @app.command("conflicts")
    def conflicts(ctx: typer.Context) -> None:
        """The files the stopped round waits on (or the held deletions)."""
        c, _info = _cli_client.client_or_exit()
        with c:
            r = c.get("/sync/stop")
            _cli_client.check(r, verbose=_verbose(ctx))
            _print_stop(r.json())

    @app.command("resolve")
    def resolve(
        ctx: typer.Context,
        path: str = typer.Argument(..., help="Vault-relative path of a conflicting file"),
        mine: bool = typer.Option(False, "--mine", help="Keep this machine's version"),
        theirs: bool = typer.Option(False, "--theirs", help="Take the other machine's version"),
        edited: bool = typer.Option(
            False, "--edited", help="Take the hand-merged copy 'coffer sync edit' opened"
        ),
    ) -> None:
        """Answer one conflicting file. Nothing is written until 'continue'."""
        choice = _answer(mine, theirs, edited)
        c, _info = _cli_client.client_or_exit()
        with c:
            r = c.post("/sync/stop/files/answer", json={"path": path, "answer": choice})
            _cli_client.check(r, verbose=_verbose(ctx))
            _print_stop(r.json())

    @app.command("edit")
    def edit(
        ctx: typer.Context,
        path: str = typer.Argument(..., help="Vault-relative path of a conflicting file"),
    ) -> None:
        """Print the path of a marked-up copy of the file to hand-merge; then
        'coffer sync resolve PATH --edited'. The vault's file is untouched."""
        c, _info = _cli_client.client_or_exit()
        with c:
            r = c.post("/sync/stop/files/editor", json={"path": path})
            _cli_client.check(r, verbose=_verbose(ctx))
            typer.echo(r.json()["editor_path"])

    @app.command("continue")
    def continue_round(ctx: typer.Context) -> None:
        """Continue the stopped round once every file has an answer."""
        c, _info = _cli_client.client_or_exit()
        with c:
            r = c.post("/sync/continue", json={})
            _cli_client.check(r, verbose=_verbose(ctx))
            print_round(r.json())

    @app.command("hold")
    def hold(
        ctx: typer.Context,
        confirm: bool = typer.Option(False, "--confirm", help="Delete the held files"),
        restore: bool = typer.Option(False, "--restore", help="Keep the held files"),
    ) -> None:
        """Show a held round, or answer it: --confirm deletes the files, --restore
        keeps them. Either continues the round."""
        if confirm and restore:
            typer.echo("choose --confirm or --restore, not both", err=True)
            raise typer.Exit(int(ExitCode.INVALID_USAGE))
        c, _info = _cli_client.client_or_exit()
        with c:
            if not (confirm or restore):
                r = c.get("/sync/stop")
                _cli_client.check(r, verbose=_verbose(ctx))
                _print_stop(r.json())
                return
            r = c.post("/sync/hold/confirm" if confirm else "/sync/hold/restore", json={})
            _cli_client.check(r, verbose=_verbose(ctx))
            print_round(r.json())

    @app.command("choose")
    def choose(
        ctx: typer.Context,
        path: str | None = typer.Argument(None, help="A file that differs (omit to list them)"),
        mine: bool = typer.Option(False, "--mine", help="Keep this machine's version"),
        theirs: bool = typer.Option(False, "--theirs", help="Take the remote's version"),
    ) -> None:
        """Settle a file a join found different on both sides."""
        c, _info = _cli_client.client_or_exit()
        with c:
            if path is None:
                r = c.get("/sync/join-choices")
            else:
                choice = _answer(mine, theirs)
                r = c.post(
                    "/sync/join-choices", json={"choices": [{"path": path, "answer": choice}]}
                )
            _cli_client.check(r, verbose=_verbose(ctx))
            files = r.json().get("files") or []
        if not files:
            _console.print("no file waits for a choice")
        for f in files:
            _console.print(f"  {f['path']}  [{f['area']}]")


__all__ = ["print_preview", "register"]

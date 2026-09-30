"""``coffer vault history | diff | show | restore | problems`` — any vault
file's versions from the terminal (spec vault-storage "Show, compare and
restore any version of a vault file", "Keep the last valid version when a hand
edit is invalid").

A PATH is relative to the vault (``skills/pdf/SKILL.md``); a folder ends in
``/`` (``skills/pdf/``). Every accepted write is a version naming who wrote
it; ``restore`` writes a version's content back as a new version, stating the
fingerprint of what is on disk now so an edit made in the meantime is refused
rather than lost.
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(
    help="The vault's history: versions, diffs, restore, and hand edits that were refused.",
    no_args_is_help=True,
)
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def _who(version: dict[str, object]) -> str:
    writer = str(version["display_writer"])
    return {"user": "you", "disk": "edited on disk"}.get(writer, writer)


@app.command("history")
def history(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="A vault file, or a folder ending in /"),
    limit: int = typer.Option(20, "--limit", help="How many versions"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List a file's or folder's versions, newest first, with who wrote each."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/vault/history", params={"path": path, "limit": limit})
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title=f"History of {data['path']}")
    for column in ("version", "when", "written by", "machine", "what"):
        table.add_column(column)
    for v in data["versions"]:
        what = str(v["summary"])
        if v["restored_from"]:
            what += f" (restored {str(v['restored_from'])[:10]})"
        table.add_row(str(v["version"])[:10], str(v["time"]), _who(v), v["machine"] or "", what)
    _console.print(table)
    if data["next_cursor"]:
        typer.echo("(older versions not shown; raise --limit)")


@app.command("diff")
def diff(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="A vault file"),
    version: str = typer.Argument(..., help="The version (from `history`)"),
) -> None:
    """Print what one version did to a file, as a unified diff."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/vault/diff", params={"path": path, "version": version})
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(r.json()["diff"] or "(no textual change)")


@app.command("show")
def show(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="A vault file"),
    version: str = typer.Argument(..., help="The version (from `history`)"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Print a file's content as one version left it."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/vault/content", params={"path": path, "version": version})
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
    elif data["binary"]:
        typer.echo(f"(binary, {data['size']} bytes)")
    else:
        typer.echo(data["content"], nl=False)


@app.command("restore")
def restore(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="A vault file, or a folder ending in /"),
    version: str = typer.Argument(..., help="The version to put back (from `history`)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask"),
) -> None:
    """Put one version back, as a new version. A folder is restored whole:
    files the version did not have are removed."""
    if not yes and not typer.confirm(f"Restore {path} to {version[:10]}?"):
        raise typer.Exit(1)
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        expected: str | None = None
        if not path.endswith("/"):
            # What is on disk now: an edit made after this read is refused.
            now = c.get("/vault/content", params={"path": path})
            if now.status_code != 404:
                _cli_client.check(now, verbose=verbose)
                expected = now.json()["fingerprint"]
        r = c.post(
            "/vault/restore",
            json={"path": path, "version": version, "expected_fingerprint": expected},
        )
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if data["version"] is None:
        typer.echo(f"{path} already matches {version[:10]}; nothing to restore")
        return
    typer.echo(f"restored {path} to {version[:10]} as {str(data['version'])[:10]}")


@app.command("problems")
def problems(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List hand edits that were refused: still on disk, not in effect until fixed."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/vault/problems")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    if not data["problems"]:
        typer.echo("no problems: every file on disk is in effect")
        return
    table = Table(title="Hand edits kept out (the last valid version stays in effect)")
    for column in ("path", "problem", "detail"):
        table.add_column(column)
    for p in data["problems"]:
        table.add_row(p["path"], p["code"], p["message"])
    _console.print(table)

"""coffer sync ... commands (spec vault-export-import vault export/import)."""

from __future__ import annotations

import pathlib
from typing import Any

import typer
from rich.console import Console

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Export this vault to a directory, or import one back")
key_app = typer.Typer(help="Out-of-band master-key transfer for new machines")
app.add_typer(key_app, name="key")
_console = Console()


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

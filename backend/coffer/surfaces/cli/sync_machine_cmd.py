"""``coffer sync machine ...`` and ``coffer sync key ...`` (spec vault-sync).

Split out of ``sync_cmd.py`` for the file-size tier. The two belong together:
the machines table is where a key-fingerprint mismatch shows up, and the key
commands are what the user reaches for the moment it does.
"""

from __future__ import annotations

import pathlib

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

machine_app = typer.Typer(help="The machines sharing this vault")
key_app = typer.Typer(help="Move the master key between your machines, out of band")

_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


# --- machines ---------------------------------------------------------------


@machine_app.command("list")
def machine_list(ctx: typer.Context) -> None:
    """Every machine sharing this vault."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/sync/machines")
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
    machines = payload.get("machines") or []
    if not machines:
        _console.print("no machines yet — run 'coffer sync now' to publish this one")
        return
    table = Table(show_header=True, header_style="bold")
    for column in ("Name", "Id", "System", "Last converged", "Key", "Agents"):
        table.add_column(column)
    for m in machines:
        key = {True: "✓", False: "✗ different", None: "—"}[m.get("key_matches")]
        table.add_row(
            f"{m['name']}  (this machine)" if m.get("is_self") else m["name"],
            m["machine_id"][:8],
            m.get("os") or "—",
            m.get("last_converged_on") or "never",
            key,
            ", ".join(m.get("agents") or []) or "—",
        )
    _console.print(table)


@machine_app.command("rename")
def machine_rename(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Rename this machine. Costs nothing: scope references the id, not the name."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch("/sync/machines/self", json={"name": name})
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
    _console.print(f"[green]renamed[/green] to {payload['name']}")


@machine_app.command("remove")
def machine_remove(ctx: typer.Context, machine_id: str = typer.Argument(...)) -> None:
    """Remove a retired machine's descriptor from the registry."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/sync/machines/{machine_id}")
        _cli_client.check(r, verbose=verbose)
    _console.print(f"[green]retired[/green] {machine_id}")


# --- master key -------------------------------------------------------------


@key_app.command("export")
def key_export(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="File to write the key material into (mode 0600)"),
) -> None:
    """Write this machine's master key out, to carry to another machine yourself.

    It never travels through the remote — that is what "out of band" means.
    """
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/key/export", json={})
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
    target = pathlib.Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload["material"], encoding="utf-8")
    target.chmod(0o600)
    _console.print(f"[green]wrote[/green] {target} (mode 0600) — move it by a channel you trust")


@key_app.command("import")
def key_import(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="File holding key material from another machine"),
) -> None:
    """Install a master key brought from another machine."""
    source = pathlib.Path(path).expanduser()
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/key/import", json={"material": source.read_text(encoding="utf-8")})
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
    locked = payload.get("locked_refs") or []
    if locked:
        _console.print(f"[yellow]still locked[/yellow]: {', '.join(locked)}")
    else:
        _console.print("[green]installed[/green] — every credential decrypts here")


@key_app.command("fingerprint")
def key_fingerprint(ctx: typer.Context) -> None:
    """This machine's key fingerprint, to compare with another machine's."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/sync/key/fingerprint")
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
    _console.print(payload.get("fingerprint") or "no master key on this machine yet")

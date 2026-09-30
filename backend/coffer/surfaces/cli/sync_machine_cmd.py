"""``coffer sync machine ...`` and ``coffer sync key ...`` (spec vault-sync).

Split out of ``sync_cmd.py`` for the file-size tier. The two belong together:
the machines table is where a key-fingerprint mismatch shows up, and the key
commands are what the user reaches for the moment it does.
"""

from __future__ import annotations

import json as _json
import pathlib

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

machine_app = typer.Typer(help="The machines sharing this vault")
key_app = typer.Typer(
    help=(
        "Install a master key brought from another machine, or compare fingerprints. "
        "Exporting a key backup is done in the Coffer desktop app."
    )
)

_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


# --- machines ---------------------------------------------------------------


@machine_app.command("list")
def machine_list(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Every machine sharing this vault."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/sync/machines")
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
        machines = payload.get("machines") or []
        if output_json:
            typer.echo(_json.dumps({"machines": machines}, indent=2))
            return
    table = Table(show_header=True, header_style="bold")
    for column in ("Name", "Id", "System", "Coffer", "Last seen", "Last round", "Key", "Agents"):
        table.add_column(column)
    for m in machines:
        key = {True: "✓", False: "✗ different", None: "—"}[m.get("key_matches")]
        agents = ", ".join(
            f"{a['type']} ({len(a.get('plugins') or [])} plugins)" for a in m.get("agents") or []
        )
        table.add_row(
            f"{m['name']}  (this machine)" if m.get("is_self") else m["name"],
            m["machine_id"][:8],
            m.get("os") or "—",
            m.get("coffer_version") or "—",
            m.get("last_round_at") or "never",
            m.get("last_round") or "—",
            key,
            agents or "—",
        )
    _console.print(table)


@machine_app.command("rename")
def machine_rename(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Rename this machine. Free: nothing keys on the label; the next round
    carries the new one."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch("/sync/machines/self", json={"name": name})
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
    _console.print(f"[green]renamed[/green] to {payload['name']}")


@machine_app.command("rm")
def machine_remove(ctx: typer.Context, machine_id: str = typer.Argument(...)) -> None:
    """Retire another machine: its descriptor goes, in a commit of yours that
    the next round pushes. A machine that syncs again comes back."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/sync/machines/{machine_id}")
        _cli_client.check(r, verbose=verbose)
    _console.print(f"[green]retired[/green] {machine_id}")


# --- master key -------------------------------------------------------------


@key_app.command("import")
def key_import(
    ctx: typer.Context,
    path: str = typer.Argument(
        ...,
        help="The key backup (coffer-master-key.cfk) exported from another machine, or a bare key",
    ),
) -> None:
    """Install a master key brought from another machine.

    A ``.cfk`` backup asks for the passphrase it was exported with, without
    echoing it.
    """
    material = pathlib.Path(path).expanduser().read_text(encoding="utf-8")
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/sync/key/import/preview", json={"material": material})
        _cli_client.check(r, verbose=verbose)
        preview = r.json()
        passphrase = None
        if preview.get("protected"):
            passphrase = typer.prompt("Passphrase", hide_input=True)
        r = c.post("/sync/key/import", json={"material": material, "passphrase": passphrase})
        _cli_client.check(r, verbose=verbose)
        payload = r.json()
    verb = "replaced" if payload.get("replaced") else "installed"
    _console.print(f"[green]{verb}[/green] — this machine now uses key {payload['fingerprint']}")
    locked = payload.get("locked_refs") or []
    if locked:
        _console.print(f"[yellow]still locked[/yellow]: {', '.join(locked)}")
    else:
        _console.print(f"every secret decrypts here ({payload.get('readable', 0)} stored)")


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

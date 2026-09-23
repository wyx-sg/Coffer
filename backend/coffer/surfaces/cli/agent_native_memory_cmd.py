"""coffer agent native-memory — read the agent's OWN native memory stores.

Every agent-workspace operation exists on BOTH REST and CLI (spec agent-registry
"Expose every agent operation through REST, CLI and the Agents page");
this is the CLI half of

  ``GET /agents/{uid}/native-memory`` → ``coffer agent native-memory <name>``
  ``GET .../native-memory/files``      → ``coffer agent native-memory-files``

Read-only, like the routes: it lists the stores, prints one store's files or one
file's contents, and never writes them. The second command takes a ``memory_dir``
the first one printed — the same identity the web surface navigates by.

Kept out of ``agent_cmd.py`` to respect the 400-line backend file cap; the same
``attach``-on-the-existing-typer pattern as ``agent_workspace_cmd.py`` keeps the
user-facing tree at ``coffer agent native-memory ...``.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def native_memory(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List the agent's OWN native per-project memory stores (read-only)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "agent", name, verbose=_verbose(ctx))
        r = c.get(f"/agents/{uid}/native-memory")
        _cli_client.check(r, verbose=_verbose(ctx))
    items = r.json()["items"]
    if output_json:
        typer.echo(_json.dumps(items, indent=2))
        return
    if not items:
        typer.echo("(no native memory)")
        return
    table = Table(title=f"Native memory — {name}")
    for col in ("Project", "Items", "Path"):
        table.add_column(col)
    for it in items:
        table.add_row(it["project"], str(it["item_count"]), it["path"] or "")
    _console.print(table)


def native_memory_files(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    memory_dir: str = typer.Option(..., "--dir", help="A memory_dir from `native-memory`."),
    path: str | None = typer.Option(
        None, "--path", help="Print this file's contents instead of the tree."
    ),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Show one native-memory store: its files, or one file's contents."""
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "agent", name, verbose=_verbose(ctx))
        if path is None:
            r = c.get(f"/agents/{uid}/native-memory/files", params={"dir": memory_dir})
        else:
            r = c.get(
                f"/agents/{uid}/native-memory/files/content",
                params={"dir": memory_dir, "path": path},
            )
        # A 404 here is about the ``dir``/``path``, not the agent: that was
        # already resolved above.
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    if path is None:
        _print_tree(data["root"], depth=0)
        return
    if data["binary"]:
        typer.echo(f"(binary file, {data['size']} bytes)")
        return
    typer.echo(data["content"])
    if data["truncated"]:
        typer.echo("(truncated — showing the start of the file)")


def _print_tree(node: dict[str, Any], *, depth: int) -> None:
    """Print a store's tree as indented lines, in the order the server sorted it."""
    indent = "  " * depth
    suffix = "/" if node["type"] == "dir" else ""
    typer.echo(f"{indent}{node['name'] or '.'}{suffix}")
    for child in node.get("children", []):
        _print_tree(child, depth=depth + 1)


def attach(agent_app: typer.Typer) -> None:
    """Register the native-memory commands on agent_cmd's existing typer."""
    agent_app.command("native-memory")(native_memory)
    agent_app.command("native-memory-files")(native_memory_files)

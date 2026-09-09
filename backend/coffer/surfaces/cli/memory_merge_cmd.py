"""`coffer memory merge-scan` / `coffer memory merge` (spec 007, FR-056-059).

Split out of ``memory_cmd.py`` (at the 400-LOC ceiling); registers its
commands on the SAME ``memory`` Typer app via import side effect (imported by
``main.py`` right after ``memory_cmd``).
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.memory_cmd import _verbose, app

_console = Console()


@app.command("merge-scan")
def merge_scan(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Scan for per-project stores that describe the SAME project: pairs
    provably equal by origin remote, the rest judged by Coffer's internal
    engine (explicit trigger; read-only)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        # The engine tier may run dozens of internal-LLM judgments in-request —
        # far beyond the client's default 15s timeout.
        r = c.post("/memory_stores/merge_scan", timeout=600.0)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    if data["engine"] == "no_model":
        typer.echo("no internal engine configured — deterministic proposals only", err=True)
    if not data["proposals"]:
        typer.echo("no merge candidates found")
        return
    table = Table(title="Merge proposals (source → target)")
    table.add_column("source")
    table.add_column("target")
    table.add_column("confidence")
    table.add_column("judged by")
    table.add_column("reason")
    for p in data["proposals"]:
        table.add_row(p["source"], p["target"], p["confidence"], p["judged_by"], p["reason"])
    _console.print(table)
    if data.get("truncated"):
        typer.echo("(engine tier truncated — re-run after merging to see more)")


@app.command("merge")
def merge(
    ctx: typer.Context,
    source: str = typer.Argument(..., help="Store merged away (retired on success)."),
    target: str = typer.Argument(..., help="Store that survives and absorbs the source."),
    no_organize: bool = typer.Option(
        False, "--no-organize", help="Skip the post-merge reorg pass on the target."
    ),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Merge one project store into another (additive — memory is gained,
    never lost), leave a no-resurrection identity alias, then organize the
    survivor with the internal engine unless --no-organize."""
    c, _info = _cli_client.client_or_exit()
    with c:
        # The default post-merge FR-059 reorg is an in-request agentic LLM pass.
        r = c.post(
            "/memory_stores/merge",
            json={"source": source, "target": target, "organize": not no_organize},
            timeout=600.0,
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(
        f"merged {source} into {data['target']}: {data['merged_files']} file(s) merged, "
        f"label {'moved' if data['label_moved'] else 'kept'}, "
        f"root {'moved' if data['root_moved'] else 'kept'}, "
        f"aliases {len(data['aliases'])}, organize: {data['reorg_status']}"
    )

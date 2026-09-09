"""``coffer knowledge`` — the non-entry lanes and the two organizing passes.

``organize`` and ``reorg`` are the internal-model passes over a scope's
``knowledge/`` lane; ``rules``, ``handoff`` and ``consolidation-log`` are the
read surfaces for the lanes that sit outside recall. Registers onto the SAME
``knowledge`` Typer app as ``knowledge_cmd`` by import side effect.
"""

from __future__ import annotations

import json as _json

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.knowledge_cmd import _verbose, app


@app.command("organize")
def organize(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Drain a scope's inbox into coherent topic documents using Coffer's
    internal model (explicit trigger)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge/{name}/organize", timeout=600.0)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    status = data["status"]
    if status == "no_model":
        typer.echo("no internal model configured — nothing organized", err=True)
        return
    if status == "empty":
        typer.echo("inbox empty — nothing to organize")
        return
    typer.echo(
        f"organized {data['items_processed']} item(s): "
        f"{data['topics_created']} created, {data['topics_updated']} updated, "
        f"{data['skipped']} skipped (model: {data.get('model')})"
    )


@app.command("reorg")
def reorg(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Reorganize a scope's topic documents: consolidate duplicates and split
    over-long docs using Coffer's internal agentic model (explicit trigger).
    Non-destructive — superseded content is archived to the recoverable
    superseded/ tombstone."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge/{name}/reorg", timeout=600.0)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    status = data["status"]
    if status == "no_model":
        typer.echo("no internal model configured — nothing reorganized", err=True)
        return
    if status == "empty":
        typer.echo("no topic documents — nothing to reorganize")
        return
    typer.echo(
        f"reorganized: {data['topics_written']} written, "
        f"{data['topics_superseded']} superseded "
        f"(before: {data['topics_before']}, after: {data['topics_after']}, "
        f"model: {data.get('model')})"
    )


@app.command("rules")
def rules(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Scope name (e.g. 'global')."),
) -> None:
    """Show a scope's rules lane (read-only)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/knowledge/{name}/rules")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(r.json().get("text") or "(no rules)")


@app.command("handoff")
def handoff(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show the saved working-state scenes ('现场'), one per git branch."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/knowledge/{name}/handoff")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    if not data["scenes"]:
        typer.echo("(no handoff)")
        return
    for scene in data["scenes"]:
        typer.echo(f"--- {scene['branch']} ({scene['updated_at']}) ---")
        typer.echo(scene["text"])


@app.command("consolidation-log")
def consolidation_log(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """Show a scope's append-only consolidation changelog."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/knowledge/{name}/consolidation-log")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(r.json().get("text") or "(no consolidation log)")

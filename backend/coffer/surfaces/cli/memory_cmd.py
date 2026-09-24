"""``coffer memory …`` — the memory layer from the terminal (spec memory
"Cover memory management on REST and the CLI").

Every command but one is a thin HTTP shell over the daemon, matching
``knowledge_cmd.py``. ``context`` is the exception: it is the exact command an
agent's own session-start hook invokes
(``domain.memory.delivery.hook_command``), so it must be fast and must never
fail a session — no detect-or-spawn, a short timeout, and any failure at all
(daemon not running, a slow response, a malformed one) degrades to printing
nothing and exiting 0. "Audit every delivery fire" exists precisely because the
previous injection layer had no such safety net and nothing said so for two
months; this command
must not repeat that by crashing a real session over its own plumbing.

Every command here takes **names** — a partition's, an agent's — because that
is what a person knows; each resolves once through ``_resolve`` to the uid the
routes address resources by, and nobody is asked to type one (ADR
resource-identity-is-an-immutable-uid).

``context`` is again the exception, and deliberately so: it takes
``--agent-uid``. Its caller is not a person but the hook entry Coffer wrote
into that agent's own settings file, months ago, and never rewrites. A uid
there is precisely what stops a rename from silently turning every session's
fire into an unattributable one — so there is no ``--agent`` and no fallback.
"""

from __future__ import annotations

import json as _json
from collections.abc import Callable
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from coffer.infrastructure.daemon.bootstrap import live_daemon
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import memory_delivery_cmd as _delivery
from coffer.surfaces.cli._resolve import resolve_uid

#: The registry kind the partition-addressing commands resolve a name against.
#: Spelled here rather than imported from ``application.memory.service`` so a
#: CLI module keeps depending on the daemon's HTTP surface and nothing deeper.
_KIND_MEMORY = "memory"

app = typer.Typer(help="Browse and manage Coffer's memory layer")
_console = Console()

#: Generous for a local loopback call, tiny next to the 10s detect-or-spawn
#: timeout `client_or_exit()` would otherwise impose on every session start.
_CONTEXT_TIMEOUT_S = 3.0


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def _echo_json_or(
    ctx: typer.Context, data: object, output_json: bool, render: Callable[[Any], None]
) -> None:
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    render(data)


@app.command("partitions")
def list_partitions(ctx: typer.Context, output_json: bool = typer.Option(False, "--json")) -> None:
    """List every partition."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/memory/partitions")
        _cli_client.check(r, verbose=_verbose(ctx))

    def render(data: dict[str, Any]) -> None:
        table = Table(title="Memory partitions")
        table.add_column("name")
        table.add_column("notes", justify="right")
        table.add_column("repository")
        for p in data["partitions"]:
            # A partition nothing can resolve to any more is called out rather
            # than hidden: only the developer can decide that repository is not
            # coming back, and an orphan that says nothing simply sits there
            # undeliverable and unmentioned ("Report unresolvable partitions").
            where = p["repository_path"] or p["repository_key"]
            table.add_row(
                p["name"],
                str(p["note_count"]),
                f"{where} (unresolvable)" if p["unresolvable"] else where,
            )
        _console.print(table)

    _echo_json_or(ctx, r.json(), output_json, render)


@app.command("notes")
def list_notes(
    ctx: typer.Context,
    partition: str = typer.Argument(..., help="Partition name (or 'global')"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List every note in one partition.

    A retired note is not in this list and is not marked in it either — it has
    left notes/ and is in RETIRED.md, which `coffer memory retired` prints.
    \f
    Requirement "Record retirements so they stick".
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, _KIND_MEMORY, partition, verbose=_verbose(ctx))
        r = c.get(f"/memory/partitions/{uid}/notes")
        _cli_client.check(r, verbose=_verbose(ctx))

    def render(data: dict[str, Any]) -> None:
        table = Table(title=f"memory {partition}")
        for col in ("slug", "title", "type", "description"):
            table.add_column(col)
        for n in data["notes"]:
            table.add_row(n["slug"], n["title"], n["type"], n["description"])
        _console.print(table)

    _echo_json_or(ctx, r.json(), output_json, render)


@app.command("note")
def show_note(
    ctx: typer.Context,
    partition: str = typer.Argument(...),
    slug: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show one note — Coffer's own text, and the entries behind it.

    The origins are printed with the absolute path of the native file each one
    was read out of, because the body is a paraphrase: a note that reads wrong
    has to be traceable back to the thing that actually said it.
    \f
    Requirement "Write notes in Coffer's own words".
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, _KIND_MEMORY, partition, verbose=_verbose(ctx))
        # ``slug`` is NOT resolved: it is the note's own file name under
        # ``notes/``, and a note is not a Resource — there is no identity below
        # the partition for it to have.
        r = c.get(f"/memory/partitions/{uid}/notes/{slug}")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"# {data['title']} ({data['key']})")
    typer.echo(f"type={data['type']} partition={data['partition']} updated={data['updated_at']}")
    if data["search_terms"]:
        typer.echo(f"search terms: {', '.join(data['search_terms'])}")
    typer.echo("")
    typer.echo(data["body"])
    typer.echo("")
    for o in data["origins"]:
        anchor = f" #{o['anchor']}" if o["anchor"] else ""
        typer.echo(f"origin: {o['agent']} <- {o['native_path']}{anchor}")


@app.command("retired")
def list_retired(
    ctx: typer.Context,
    partition: str = typer.Argument(..., help="Partition name (or 'global')"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show what this partition retired, and why.

    Newest first. ``RETIRED.md`` is not a bin: the material a retired note was
    built from still lives in the agent's own memory, so without the record the
    next distil pass would re-open the note the last one removed. A row with no
    slug is one where a pass kept nothing from an entry at all.
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, _KIND_MEMORY, partition, verbose=_verbose(ctx))
        r = c.get(f"/memory/partitions/{uid}/retired")
        _cli_client.check(r, verbose=_verbose(ctx))

    def render(data: dict[str, Any]) -> None:
        table = Table(title=f"memory {partition} — retired")
        for col in ("slug", "title", "replaced by", "reason"):
            table.add_column(col)
        for rec in data["retired"]:
            table.add_row(rec["slug"], rec["title"], rec["replaced_by"], rec["reason"])
        _console.print(table)

    _echo_json_or(ctx, r.json(), output_json, render)


@app.command("ls")
def list_files(
    ctx: typer.Context,
    partition: str = typer.Argument(..., help="Partition name (or 'global')"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List a partition's own directory as a tree.

    The whole tree rather than one level, unlike `coffer knowledge ls`: a
    partition is two levels deep by construction (`MEMORY.md`, `RETIRED.md`, a
    `notes/` folder and a hidden `.raw/`), so stopping at the root would never
    show a note. `.raw/` is marked `derived` — it is what was read out of the
    agents, verbatim, and it is the distil pass's input rather than its output.
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, _KIND_MEMORY, partition, verbose=_verbose(ctx))
        r = c.get(f"/memory/partitions/{uid}/files")
        _cli_client.check(r, verbose=_verbose(ctx))

    def render(data: dict[str, Any]) -> None:
        table = Table(title=f"memory {partition}")
        table.add_column("path")
        table.add_column("type")
        table.add_column("size", justify="right")
        for node in _walk(data["root"]):
            size = node.get("size")
            path = node["path"] + ("/" if node["type"] == "dir" else "")
            table.add_row(
                f"{path} (derived)" if node["derived"] else path,
                node["type"],
                "" if size is None else str(size),
            )
        _console.print(table)

    _echo_json_or(ctx, r.json(), output_json, render)


def _walk(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Every descendant of ``node``, depth-first, excluding the root itself.

    The root's own path is ``""`` — a row for it would say nothing and sort
    above everything, so it is the one node left out.
    """
    out: list[dict[str, Any]] = []
    for child in node.get("children", []):
        out.append(child)
        out.extend(_walk(child))
    return out


@app.command("read")
def read_file(
    ctx: typer.Context,
    partition: str = typer.Argument(..., help="Partition name (or 'global')"),
    path: str = typer.Argument(..., help="File path inside the partition, e.g. notes/foo.md"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Print one file out of a partition's directory.

    Read-only: everything under ~/.coffer/memory/ is derived, so there is no
    matching write for an edit to survive. --json carries the absolute paths
    an editor or a file manager needs.
    \f
    Requirement "Keep the memory tree derived and local".
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, _KIND_MEMORY, partition, verbose=_verbose(ctx))
        # ``path`` stays as typed — it is a filesystem path inside the
        # partition's own directory, not a reference to anything registered.
        r = c.get(f"/memory/partitions/{uid}/files/content", params={"path": path})
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    if data["binary"]:
        typer.echo(f"{data['path']}: binary file, {data['size']} bytes")
        return
    typer.echo(data["content"])
    if data["truncated"]:
        typer.echo("… truncated", err=True)


@app.command("sync")
def sync(ctx: typer.Context, output_json: bool = typer.Option(False, "--json")) -> None:
    """Run aggregation: read every registered agent's native memory."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/memory/sync")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2) if output_json else r.text)


@app.command("distil")
def distil(
    ctx: typer.Context,
    partition: str = typer.Argument(..., help="Partition to distil"),
) -> None:
    """Run the distil pass by hand over one partition.

    Only one pass per partition runs at a time, whoever started it: a request
    made while the unattended sweep already holds this partition is refused
    rather than queued.
    \f
    Refused with ``UPKEEP_ALREADY_RUNNING`` ("Run one distil pass per partition
    at a time").
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, _KIND_MEMORY, partition, verbose=_verbose(ctx))
        r = c.post(f"/memory/partitions/{uid}/distil")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2))


@app.command("context")
def context(
    agent_uid: str = typer.Option(
        ..., "--agent-uid", help="The uid of the agent whose hook is firing"
    ),
    cwd: str = typer.Option(..., "--cwd", help="The session's working directory"),
    ceiling_tokens: int = typer.Option(0, "--ceiling-tokens", help="0 = the server's default"),
) -> None:
    """Print the composed session-start context to stdout.

    The installed session-start hook runs this; you rarely need to. It prints
    nothing, and exits 0, when the daemon is not running.
    \f
    This is exactly what an installed session-start hook invokes
    (``domain.memory.delivery.hook_command``) — see the module docstring for
    why every failure here is silent rather than raised.

    ``--agent-uid`` says who fired, and only that: the payload is the same for
    every agent, and the uid travels so the daemon can record the fire against
    it ("Audit every delivery fire"). It is still required, because an
    unattributed fire is a hook
    nobody can tell is working.

    It is the **one** command in this group that does not take a name, because
    it is the one whose caller is not a person. The value arrives from a string
    Coffer wrote into the agent's settings file at install time and never
    revisits; a name there would keep pointing at a label the user is free to
    change, and the fire would then be attributed to nothing. There is
    deliberately no ``--agent`` alias to fall back to — two spellings would put
    the rename hazard straight back (ADR
    resource-identity-is-an-immutable-uid).
    """
    try:
        info = live_daemon()
        if info is None:
            return
        payload: dict[str, object] = {
            "agent_uid": agent_uid,
            "cwd": cwd,
            "record_fired": True,
        }
        if ceiling_tokens > 0:
            payload["ceiling_tokens"] = ceiling_tokens
        resp = httpx.post(
            f"http://127.0.0.1:{info.port}/api/v1/memory/context",
            json=payload,
            headers={"X-Coffer-Token": info.token, "X-Coffer-Actor": "cli"},
            timeout=_CONTEXT_TIMEOUT_S,
        )
        if resp.status_code != 200:
            return
        text = resp.json().get("text")
        if text:
            typer.echo(text)
    except Exception:
        return


# --- delivery commands (memory_delivery_cmd.py, to respect the size cap) ---
#
# Split along the seam that was already there: every command above reads or
# rewrites Coffer's own memory tree, while those three write into an AGENT's
# settings file. The commands themselves are unmoved — ``coffer memory
# delivery``, ``delivery-install``, ``delivery-remove`` — because they are
# registered on this same typer.

_delivery.attach(app)

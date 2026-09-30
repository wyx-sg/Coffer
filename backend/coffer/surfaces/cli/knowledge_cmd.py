"""``coffer knowledge …`` — knowledge collections from the terminal (spec
knowledge "Cover knowledge management on REST and the CLI").

``show`` and ``rm`` are the lifecycle verbs every kind shares
(``_kind_verbs``). ``list``, ``add`` and ``edit`` are the kind's own: ``list`` reads
``/knowledge/collections``, which counts each collection's documents and its
items waiting to be curated and reads its description off its ``README.md``; ``add``
creates the directory and the README, which the generic create route does not
(the kind is not generic-creatable); ``edit`` renames a collection (its
directory moves with it) or rewrites its description, the README's opening
paragraph. A collection has no title: it is shown by its folder name.
``write``, ``upload`` and ``curate`` feed
and run curation. There is no ``scope``, ``enable`` or ``disable``: every collection is
served to every agent ("Serve every collection to every agent").

A collection's documents are plain Markdown, so this group has no command that
lists, prints, saves or deletes one: ``coffer path knowledge [<collection>]`` names
the directory, and a person reads, greps, edits and deletes the files there
with their own tools ("Keep direct file edits a complete way to change
knowledge").

Every command takes a collection **name** (or a uid) and resolves it once
through ``_resolve`` (ADR resource-identity-is-an-immutable-uid).
"""

from __future__ import annotations

import contextlib
import json as _json
import pathlib
import sys
import threading
from collections.abc import Iterator
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import KindVerbs, label, register_kind_verbs
from coffer.surfaces.cli._resolve import resolve_uid
from coffer.surfaces.cli.knowledge_history_cmd import register_history_commands

#: The registry kind. Spelled here rather than imported from the application
#: layer, so a CLI module depends on the daemon's HTTP surface and nothing deeper.
KIND = "knowledge"

app = typer.Typer(
    help=(
        "Manage Coffer's knowledge collections, the Markdown under "
        "~/.coffer/knowledge/<collection>/ (`coffer path knowledge` prints it). "
        "Each collection is one tree of documents you and Coffer write together: "
        "read, grep and edit them with your own tools, and add new knowledge with "
        "`write` or `upload`: it waits as an item until Coffer curates it into the "
        "documents. `history`, `changes` and `undo` show and reverse what changed."
    )
)
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


@app.command("list")
def list_collections(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List every collection, with its documents and the items waiting to be curated."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/knowledge/collections")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title="Knowledge collections")
    table.add_column("name")
    # Waiting is items still to be curated — what an agent cannot
    # read yet (spec knowledge "Hide dot-prefixed entries except the inbox").
    table.add_column("documents", justify="right")
    table.add_column("waiting", justify="right")
    table.add_column("description")
    for entry in data["collections"]:
        table.add_row(
            label(entry),
            str(entry["document_count"]),
            str(entry["pending_count"]),
            entry["description"],
        )
    _console.print(table)


register_kind_verbs(app, KindVerbs(kind=KIND, noun="collection", verbs=frozenset({"show"})))


@app.command("add")
def add_collection(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Collection name (one path segment)"),
    description: str = typer.Option(
        "", "--description", "-d", help="Written as the opening paragraph of its README.md"
    ),
) -> None:
    """Create a collection. Nothing else creates one."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            "/knowledge/collections",
            json={"name": name, "description": description or None},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"added: collection {name}")


@app.command("edit")
def edit_collection(
    ctx: typer.Context,
    ref: str = typer.Argument(..., metavar="NAME", help="Name or uid"),
    new_name: str | None = typer.Option(None, "--name", help="New name (the folder moves)"),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Rewrite the opening paragraph of its README.md"
    ),
) -> None:
    """Rename a collection (its directory moves with it) or rewrite its description."""
    if new_name is None and not description:
        typer.echo("nothing to change: name at least one option", err=True)
        raise typer.Exit(2)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, KIND, ref, verbose=_verbose(ctx))
        if description:
            r = c.put(
                f"/knowledge/collections/{uid}/description", json={"description": description}
            )
            _cli_client.check(r, verbose=_verbose(ctx))
        if new_name is not None:
            r = c.patch(f"/resources/{uid}", json={"name": new_name})
            _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"updated: collection {new_name or ref}")


register_kind_verbs(
    app,
    KindVerbs(
        kind=KIND,
        noun="collection",
        verbs=frozenset({"rm"}),
        titled=False,
        help={"rm": "Remove a collection and its directory (`restore --deleted` brings it back)."},
    ),
)


@app.command("write")
def submit_material(
    ctx: typer.Context,
    title: str = typer.Option(..., "--title", "-t"),
    description: str = typer.Option(..., "--description", "-d", help="What it is about"),
    body: str = typer.Option("", "--body", "-b"),
    collection: str = typer.Option(..., "--in", help="Collection to add it to"),
) -> None:
    """Add new knowledge as an item. Coffer curates it into the documents."""
    payload = {
        "title": title,
        "description": description,
        "body": body,
        "collection": collection,
    }
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/knowledge/material", json=payload)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_submission(r.json()))


def _submission(data: dict[str, object]) -> str:
    """One line saying what became of the item."""
    if data.get("path"):
        return str(data["path"])
    return f"queued in {data['collection']} — waiting to be curated into the documents"


@app.command("upload")
def upload(
    ctx: typer.Context,
    file: pathlib.Path = typer.Argument(  # noqa: B008 — typer option declaration
        ..., help="Document to ingest", exists=True
    ),
    collection: str = typer.Option(..., "--collection", help="Collection to ingest it into"),
) -> None:
    """Convert a document to Markdown and add what it says to a collection.

    The extracted text becomes an item that curation folds into the documents;
    neither the original nor the extracted file is kept.

    \f
    Requirement "Convert uploads into material without keeping them".
    """
    form: dict[str, str] = {"collection": collection}
    c, _info = _cli_client.client_or_exit()
    with c:
        with file.open("rb") as fh:
            r = c.post(
                "/knowledge/upload",
                data=form,
                files={"file": (file.name, fh)},
            )
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    typer.echo(_submission({**data, "collection": collection}))


@app.command("curate")
def curate(
    ctx: typer.Context,
    collection: str = typer.Argument(..., help="Collection to curate"),
    document: str = typer.Option(
        "", "--document", help="Curate just this document (a path under the collection)"
    ),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Curate a collection now: one pass per pending item until none is left.

    Items waiting in the inbox go first, oldest first, then documents edited
    since curation last saw them. Each pass is bounded and reports its status —
    ok, truncated (cut off; its item stays pending), too_large, failed — and the
    run stops at the first failed pass, leaving the rest pending. With no
    model configured, the inbox becomes documents as it stands (no_model).
    A run already curating the same collection is refused rather than queued.

    \f
    Requirement "Run curation on a sweep and on demand".
    """
    # The route takes the document in the body, not the query string: a path
    # is content, and a silently-ignored query param would look like a pass
    # that simply chose a different item.
    body = {"document": document} if document else {}
    c, _info = _cli_client.client_or_exit()
    with c:
        # Addressed by identity: a run takes minutes over a whole corpus, so it
        # is aimed at the collection's uid, looked up here once from the name.
        uid = resolve_uid(c, KIND, collection, verbose=_verbose(ctx))
        with _live_progress(c, uid, enabled=not output_json and sys.stderr.isatty()):
            r = c.post(f"/knowledge/collections/{uid}/curate", json=body, timeout=None)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    total = data["total"]
    for n, outcome in enumerate(data["passes"], start=1):
        typer.echo(f"{n} of {max(total, len(data['passes']))}: {_pass_line(outcome)}")
    typer.echo(_run_line(data))


def _pass_line(outcome: dict[str, Any]) -> str:
    status = str(outcome["status"])
    item = str(outcome.get("item") or "")
    if status in {"ok", "truncated"}:
        detail = f"{outcome.get('written', 0)} written, {outcome.get('retired', 0)} retired"
        return f"{status} {item} ({detail})".replace("  ", " ")
    promoted = outcome.get("promoted") or []
    if promoted:
        return f"{status} {item} — became {', '.join(map(str, promoted))}".replace("  ", " ")
    return f"{status} {item}".strip()


def _run_line(data: dict[str, Any]) -> str:
    status = data["status"]
    if status == "up_to_date":
        return f"{data['collection']}: nothing to curate"
    if status == "no_model":
        return f"{data['collection']}: Coffer's model is not set; items became documents as is"
    if status == "failed":
        return f"{data['collection']}: stopped at a failed pass — the rest is still pending"
    return f"{data['collection']}: curated {len(data['passes'])} of {data['total']}"


@contextlib.contextmanager
def _live_progress(c: httpx.Client, uid: str, *, enabled: bool) -> Iterator[None]:
    """Print ``curating n of m`` to stderr while the run's request is open,
    read off the in-flight list (``GET /upkeep/runs``) the run updates."""
    if not enabled:
        yield
        return
    stop = threading.Event()

    def poll() -> None:
        seen: tuple[object, object] | None = None
        with httpx.Client(base_url=c.base_url, headers=c.headers, timeout=5) as poller:
            while not stop.wait(1.0):
                with contextlib.suppress(Exception):
                    runs = poller.get("/upkeep/runs").json()["runs"]
                    mine = next((x for x in runs if x["kind"] == KIND and x["name"] == uid), None)
                    if mine and mine.get("total") and (mine["done"], mine["total"]) != seen:
                        seen = (mine["done"], mine["total"])
                        typer.echo(f"curating… {mine['done']} of {mine['total']} done", err=True)

    worker = threading.Thread(target=poll, daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=2)


# The history commands (``history``, ``restore``, ``changes``, ``undo``) live
# beside this module for the file-size ceiling and join this group here.
register_history_commands(app, console=_console, verbose=_verbose)

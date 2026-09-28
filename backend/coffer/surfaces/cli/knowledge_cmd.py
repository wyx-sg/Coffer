"""``coffer knowledge …`` — knowledge collections from the terminal (spec
knowledge "Cover collection management on REST and the CLI").

``show``, ``edit``, ``rm``, ``enable`` and ``disable`` are the lifecycle verbs
every kind shares (``_kind_verbs``). ``list`` and ``add`` are the kind's own:
``list`` reads ``/knowledge/collections``, which counts each collection's
documents and its unmerged material and reads its description off its
``README.md``; ``add`` creates the directory and the README, which the generic
create route does not (the kind is not generic-creatable). ``write``,
``upload`` and ``curate`` feed and run curation. There is no ``scope``: a
collection's one switch is ``enabled`` ("Gate collections with enabled
alone").

A collection's documents are plain Markdown, so this group has no command that
lists, prints or deletes one: ``coffer path knowledge [<collection>]`` names
the directory, and a person reads, greps, edits and deletes the files there
with their own tools ("Keep direct file edits a complete way to change
knowledge").

Every command takes a collection **name** (or a uid) and resolves it once
through ``_resolve`` (ADR resource-identity-is-an-immutable-uid).
"""

from __future__ import annotations

import json as _json
import pathlib

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import KindVerbs, label, register_kind_verbs
from coffer.surfaces.cli._resolve import resolve_uid

#: The registry kind. Spelled here rather than imported from the application
#: layer, so a CLI module depends on the daemon's HTTP surface and nothing deeper.
KIND = "knowledge"

app = typer.Typer(
    help=(
        "Manage Coffer's knowledge collections, the Markdown under "
        "~/.coffer/knowledge/<collection>/ (`coffer path knowledge` prints it). "
        "Each collection is one tree of documents you and Coffer write together: "
        "read, grep and edit them with your own tools, and add new knowledge with "
        "`write` or `upload` — Coffer's curation pass merges it into the documents."
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
    """List every collection, with its documents and unmerged material."""
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
    # Pending is material still waiting to be merged — what an agent cannot
    # read yet (spec knowledge "Hide dot-prefixed entries except the inbox").
    table.add_column("documents", justify="right")
    table.add_column("pending", justify="right")
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
    title: str | None = typer.Option(None, "--title", help="Display title (≤80 chars)"),
) -> None:
    """Create a collection. Nothing else creates one."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            "/knowledge/collections",
            json={"name": name, "description": description or None},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
        if title:
            t = c.patch(f"/resources/{r.json()['uid']}", json={"title": title})
            _cli_client.check(t, verbose=_verbose(ctx))
    typer.echo(f"added: collection {name}")


register_kind_verbs(
    app,
    KindVerbs(
        kind=KIND,
        noun="collection",
        verbs=frozenset({"edit", "rm", "enable", "disable"}),
        help={
            "edit": "Rename a collection (its directory moves with it) or set its title.",
            "rm": "Remove a collection and its directory.",
        },
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
    """Add new knowledge. Coffer's curation pass merges it into the documents."""
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
    """One line saying what became of the material."""
    if data.get("path"):
        return str(data["path"])
    return f"queued in {data['collection']} — curation merges it into the documents"


@app.command("upload")
def upload(
    ctx: typer.Context,
    file: pathlib.Path = typer.Argument(  # noqa: B008 — typer option declaration
        ..., help="Document to ingest", exists=True
    ),
    collection: str = typer.Option(..., "--collection", help="Collection to ingest it into"),
) -> None:
    """Convert a document to Markdown and add what it says to a collection.

    The extracted text is new material: curation merges it into the documents,
    and neither the original nor the extracted file is kept.

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
        "", "--document", help="Carry one edited document through rather than the next pending item"
    ),
) -> None:
    """Run a curation pass by hand over one collection.

    A pass is bounded and reports why it stopped, so the status is the answer:
    ok; truncated when the pass was cut off (its item stays pending);
    up_to_date; no_model when Coffer's own model is not configured; too_large;
    or failed. A pass already running over the same collection is refused
    rather than queued.

    \f
    Requirements "Promote material directly when no model is configured" and
    "Run one pass per collection at a time".
    """
    # The route takes the document in the body, not the query string: a path
    # is content, and a silently-ignored query param would look like a pass
    # that simply chose a different item.
    body = {"document": document} if document else {}
    c, _info = _cli_client.client_or_exit()
    with c:
        # The one command in this group addressed by identity rather than by a
        # path: a pass runs for minutes over a whole corpus, so it is aimed at
        # the collection's uid. The lookup happens here, once, so the person
        # still types the name they gave the collection.
        uid = resolve_uid(c, KIND, collection, verbose=_verbose(ctx))
        r = c.post(f"/knowledge/collections/{uid}/curate", json=body)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2))

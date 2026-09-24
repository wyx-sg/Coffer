"""``coffer knowledge …`` — the knowledge directory from the terminal.

Thin HTTP shells over the daemon, matching the other CLI groups and their
exit-code mapping (``_cli_client.check``).

This group serves the **human**, which is why it still browses and reads while
the MCP gateway exposes nothing but ``coffer__write`` (spec knowledge "Expose
exactly one knowledge tool").
The two are not the same surface and do not answer to the same rule: an agent
has ``Read`` and ``Grep`` of its own and is handed absolute paths by the
delivered skill, so a retrieval tool for it would be a tool it never
remembers to call; a person at a prompt has neither the paths nor the daemon's
scope resolution in front of them. What this group must cover is the list in
"Cover collection management on REST and the CLI" — create a collection, list
a level, read a document, submit material, upload a document, delete a
document, trigger curation — and nothing beyond it. There is
deliberately no ``grep`` and no ``search`` command: the corpus is plain
Markdown under ``~/.coffer/knowledge/``, so a person's own ``grep`` is already
better than anything this group could wrap, and the group's help says where
the files are so reaching for it is obvious.

Every command here takes a **name**, because that is what a person knows. Where
a route is addressed by the collection's uid — only ``curate`` is — the name is
resolved once through ``_resolve`` and never asked of the user (ADR
resource-identity-is-an-immutable-uid). The rest take filesystem paths, whose
first segment is the collection's directory, and those are names on both sides
of the wire.
"""

from __future__ import annotations

import json as _json
import pathlib

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

app = typer.Typer(
    help=(
        "Browse and edit Coffer's knowledge, the Markdown under "
        "~/.coffer/knowledge/<collection>/. Each collection is one tree of "
        "documents you and Coffer write together: edit them in your own editor, "
        "and add new knowledge with `write` or `upload` — Coffer's curation pass "
        "merges it into the documents. Grep the directory with your own tools; "
        "there is no search command."
    )
)
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


@app.command("collections")
def list_collections(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json"),
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
            entry["name"],
            str(entry["document_count"]),
            str(entry["pending_count"]),
            entry["description"],
        )
    _console.print(table)


@app.command("create")
def create_collection(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Collection name (one path segment)"),
    description: str = typer.Option("", "--description", "-d"),
) -> None:
    """Create a collection. Nothing else creates one."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            "/knowledge/collections",
            json={"name": name, "description": description or None},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"created collection {name}")


@app.command("ls")
def list_level(
    ctx: typer.Context,
    path: str = typer.Argument(
        ..., help="A collection or a folder inside one, e.g. payments or payments/apis"
    ),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List one level of a collection — folders and files, not the whole tree."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/knowledge/tree", params={"path": path})
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title=f"knowledge:{data['path']}")
    table.add_column("path")
    table.add_column("title")
    table.add_column("description")
    for directory in data["directories"]:
        table.add_row(f"{directory['path']}/", "", f"{directory['file_count']} files")
    for entry in data["files"]:
        table.add_row(entry["path"], entry["title"], entry["description"])
    _console.print(table)


@app.command("read")
def read_file(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="File path under the knowledge root"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Print a document."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/knowledge/file", params={"path": path})
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(data["body"])


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


@app.command("delete")
def delete_document(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Document path, e.g. payments/gateway.md"),
) -> None:
    """Delete a document."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete("/knowledge/file", params={"path": path})
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"deleted {path}")


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
        uid = resolve_uid(c, "knowledge", collection, verbose=_verbose(ctx))
        r = c.post(f"/knowledge/collections/{uid}/curate", json=body)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2))

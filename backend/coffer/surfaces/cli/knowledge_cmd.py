"""``coffer knowledge …`` — the knowledge directory from the terminal.

Thin HTTP shells over the daemon, matching the other CLI groups and their
exit-code mapping (``_cli_client.check``).

This group serves the **human**, which is why it still browses and reads while
the MCP gateway exposes nothing but ``coffer__write`` (spec knowledge FR-033).
The two are not the same surface and do not answer to the same rule: an agent
has ``Read`` and ``Grep`` of its own and is handed absolute paths by the
delivered skill, so a retrieval tool for it would be a tool it never
remembers to call; a person at a prompt has neither the paths nor the daemon's
scope resolution in front of them. What this group must cover is FR-039's
list — create a collection, list a lane, read a file, write a source, upload a
document, delete a source, trigger curation — and nothing beyond it. There is
deliberately no ``grep`` and no ``search`` command: the corpus is plain
Markdown under ``~/.coffer/knowledge/``, so a person's own ``grep`` is already
better than anything this group could wrap, and the group's help says where
the files are so reaching for it is obvious.
"""

from __future__ import annotations

import json as _json
import pathlib

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(
    help=(
        "Browse and edit Coffer's knowledge, the Markdown under "
        "~/.coffer/knowledge/<collection>/. Each collection has two lanes: you "
        "write source material into sources/, and Coffer's curation pass "
        "derives topics/ from it — topics/ is what an agent reads. Grep the "
        "directory with your own tools; there is no search command."
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
    """List every collection, with what each lane holds."""
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
    # The two counts are the one honest picture of a collection's state: a
    # collection with sources and no topics has not been curated yet, and
    # that is the difference between material Coffer holds and material an
    # agent can reach (spec knowledge FR-021).
    table.add_column("sources", justify="right")
    table.add_column("topics", justify="right")
    table.add_column("description")
    for entry in data["collections"]:
        table.add_row(
            entry["name"],
            str(entry["source_count"]),
            str(entry["topic_count"]),
            entry["description"],
        )
    _console.print(table)


@app.command("create")
def create_collection(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Collection name (one path segment)"),
    description: str = typer.Option("", "--description", "-d"),
) -> None:
    """Create a collection and its two lanes. Nothing else creates one."""
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
        ..., help="Path inside a lane, e.g. shopee/sources or shopee/topics/apis"
    ),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List one level of one lane — folders and files, not the whole tree."""
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
    """Print a file from either lane."""
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
def write_source(
    ctx: typer.Context,
    title: str = typer.Option(..., "--title", "-t"),
    description: str = typer.Option(..., "--description", "-d", help="What the source is about"),
    body: str = typer.Option("", "--body", "-b"),
    collection: str = typer.Option(..., "--in", help="Collection to file it in"),
    folder: str = typer.Option("", "--folder", help="Subfolder inside sources/, if any"),
) -> None:
    """Write a source. Only curation writes topics/ (spec knowledge FR-013)."""
    # The `sources/` segment is the layer's, not the caller's, so it is never
    # spelled here: the lane a write lands in is not a thing a surface gets to
    # choose (FR-013).
    payload = {
        "title": title,
        "description": description,
        "body": body,
        "collection": collection,
        "folder": folder or None,
    }
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.put("/knowledge/file", json=payload)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(r.json()["path"])


@app.command("delete")
def delete_source(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Source path, e.g. shopee/sources/gateway.md"),
) -> None:
    """Delete a source. A topic document cannot be deleted by hand (FR-020)."""
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
    folder: str = typer.Option("", "--folder", help="Subfolder inside sources/, if any"),
) -> None:
    """Convert a document to Markdown and file both it and the original.

    Both land in the collection's ``sources/``, the original under its own
    name and byte-identical to what was sent (FR-016).
    """
    # httpx encodes a `None` form value as an empty field rather than
    # omitting it, which would arrive as "" and not the server's own
    # default — so an empty --folder is left out of the body entirely.
    form: dict[str, str] = {"collection": collection}
    if folder:
        form["folder"] = folder
    c, _info = _cli_client.client_or_exit()
    with c:
        with file.open("rb") as fh:
            r = c.post(
                "/knowledge/upload",
                data=form,
                files={"file": (file.name, fh)},
            )
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(r.json()["path"])


@app.command("curate")
def curate(
    ctx: typer.Context,
    collection: str = typer.Argument(..., help="Collection to curate"),
    source: str = typer.Option(
        "", "--source", help="Curate one source path rather than everything pending"
    ),
) -> None:
    """Run a curation pass by hand over one collection.

    A pass is bounded and reports why it stopped, so the status is the answer:
    ``ok``, ``up_to_date``, ``no_model`` when no internal connection is
    configured (FR-029), ``too_large``, or ``failed``. A pass already in
    flight over the same collection is refused rather than queued (FR-030).
    """
    # The route takes the source in the body, not the query string: a path is
    # content, and a silently-ignored query param would look like a pass that
    # simply chose a different source.
    body = {"source": source} if source else {}
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge/collections/{collection}/curate", json=body)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2))

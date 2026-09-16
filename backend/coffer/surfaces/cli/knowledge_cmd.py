"""``coffer knowledge …`` — the knowledge directory from the terminal.

Thin HTTP shells over the daemon, matching the other CLI groups and their
exit-code mapping (``_cli_client.check``). ``search`` and ``upload`` round out
the group with literal search and document ingestion (spec knowledge FR-034).
"""

from __future__ import annotations

import json as _json
import pathlib

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Browse and edit Coffer's knowledge")
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


@app.command("collections")
def list_collections(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List every collection."""
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
    table.add_column("files", justify="right")
    table.add_column("description")
    for entry in data["collections"]:
        table.add_row(entry["name"], str(entry["file_count"]), entry["description"])
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
    path: str = typer.Argument(..., help="Path under the knowledge root, e.g. shopee/account"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List one level of the catalogue — folders and files, not the whole tree."""
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
    """Print a file."""
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
def write_file(
    ctx: typer.Context,
    title: str = typer.Option(..., "--title", "-t"),
    description: str = typer.Option(..., "--description", "-d", help="What makes it findable"),
    body: str = typer.Option("", "--body", "-b"),
    directory: str = typer.Option("", "--in", help="Collection or folder to create it in"),
    path: str = typer.Option("", "--path", help="Existing file to replace"),
) -> None:
    """Create a file, or replace an existing one."""
    if bool(directory) == bool(path):
        typer.echo("give exactly one of --in or --path", err=True)
        raise typer.Exit(2)
    payload = {
        "title": title,
        "description": description,
        "body": body,
        "directory": directory or None,
        "path": path or None,
    }
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.put("/knowledge/file", json=payload)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(r.json()["path"])


@app.command("delete")
def delete_file(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="File path under the knowledge root"),
) -> None:
    """Delete a file."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete("/knowledge/file", params={"path": path})
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"deleted {path}")


@app.command("grep")
def grep(
    ctx: typer.Context,
    pattern: str = typer.Argument(..., help="Literal string or regex"),
    collection: str = typer.Option("", "--in", help="Restrict to one collection"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Search the files themselves. There is no index; this is the search."""
    params: dict[str, str] = {"pattern": pattern}
    if collection:
        params["collection"] = collection
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/knowledge/grep", params=params)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    for match in data["matches"]:
        typer.echo(f"{match['path']}:{match['line_number']}: {match['line']}")
    if data["truncated"]:
        typer.echo("… more matches exist", err=True)


@app.command("tidy")
def tidy(
    ctx: typer.Context,
    collection: str = typer.Argument(..., help="Collection to tidy"),
) -> None:
    """Run the tidy pass by hand over one collection."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge/collections/{collection}/tidy")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2))


@app.command("search")
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="The word, phrase or regex to look for"),
    collection: str = typer.Option("", "--collection", help="Restrict to one collection"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Find the files a word or phrase appears in, with the lines that matched."""
    payload = {"query": query, "collection": collection or None}
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/knowledge/search", json=payload)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    for hit in data["results"]:
        typer.echo(f"{hit['path']}  {hit['title']}")
        for line in hit["lines"]:
            typer.echo(f"  {line['line_number']}: {line['line']}")


@app.command("upload")
def upload(
    ctx: typer.Context,
    file: pathlib.Path = typer.Argument(  # noqa: B008 — typer option declaration
        ..., help="Document to ingest", exists=True
    ),
    collection: str = typer.Option(..., "--collection", help="Collection to ingest it into"),
    directory: str = typer.Option("", "--directory", help="Folder inside the collection, if any"),
) -> None:
    """Convert a document to Markdown and file it into a collection."""
    # httpx encodes a `None` form value as an empty field rather than
    # omitting it, which would arrive as "" and not the server's own
    # default — so an empty --directory is left out of the body entirely.
    form: dict[str, str] = {"collection": collection}
    if directory:
        form["directory"] = directory
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

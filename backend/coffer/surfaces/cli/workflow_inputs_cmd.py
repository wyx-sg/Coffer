"""``coffer workflow run inputs …`` — what a run reads, from the terminal.

Split out of ``workflow_cmd`` for the file-size cap, and the seam is a real one:
these four commands are the only ones in the group that do not move the run.
Mounting a collection, uploading a file and unmounting either are things the
developer does *alongside* a run at any point in its life (spec workflow "Add
and remove inputs at any point in a run"), which is why none of them carries a
``--version`` — an input is not a transition, and two people mounting two
collections have not conflicted.

``add`` takes its input as ``kind:ref`` — one spelling for every kind a run can
read, so the thing a person learns once reads the same whether they are mounting
a collection, a link or a repository. The file kind is the exception and has
``upload``, because it is the one whose ref the store chooses rather than the
developer.
"""

from __future__ import annotations

import json as _json
import pathlib
from typing import Any
from urllib.parse import quote

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="What a run reads — collections, uploaded files and links")
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def _render(payload: Any) -> None:
    items = payload.get("items", [])
    if not items:
        typer.echo("nothing mounted — `coffer workflow run inputs add` mounts something")
        return
    table = Table(show_header=True, header_style="bold")
    for column in ("kind", "ref", "label", "size"):
        table.add_column(column)
    for item in items:
        size = item.get("size")
        table.add_row(
            item["kind"],
            item["ref"],
            item.get("label") or "—",
            "—" if size is None else f"{size} B",
        )
    _console.print(table)


def _echo(payload: Any, output_json: bool) -> None:
    if output_json:
        typer.echo(_json.dumps(payload, indent=2))
    else:
        _render(payload)


@app.command("list")
def list_inputs(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Everything this run reads."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/workflow/runs/{run_id}/inputs")
        _cli_client.check(r, verbose=_verbose(ctx))
        payload = r.json()
    _echo(payload, output_json)


@app.command("add")
def add_input(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    ref: str = typer.Argument(
        ..., help="kind:ref — knowledge:<collection>, link:<url> or repo:<path>"
    ),
    label: str | None = typer.Option(None, "--label", help="What to call it in a node's context"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Mount a knowledge collection or a link. Every node that opens afterwards reads it."""
    kind, _, value = ref.partition(":")
    if not value:
        typer.echo(f"an input must look like kind:ref, got {ref!r}", err=True)
        raise typer.Exit(2)
    body: dict[str, Any] = {"kind": kind, "ref": value}
    if label:
        body["label"] = label
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/workflow/runs/{run_id}/inputs", json=body)
        _cli_client.check(r, verbose=_verbose(ctx))
        payload = r.json()
    _echo(payload, output_json)


@app.command("upload")
def upload_input(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    file: pathlib.Path = typer.Argument(  # noqa: B008 — typer option declaration
        ..., help="The file this run should be able to read", exists=True
    ),
    label: str | None = typer.Option(None, "--label"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Upload a file into the run's own directory, where its nodes can open it."""
    # httpx encodes a `None` form value as an empty field rather than omitting
    # it, so an absent --label is left out of the body entirely.
    form: dict[str, str] = {"label": label} if label else {}
    c, _info = _cli_client.client_or_exit()
    with c:
        with file.open("rb") as fh:
            r = c.post(
                f"/workflow/runs/{run_id}/inputs/uploads",
                data=form,
                files={"file": (file.name, fh)},
            )
        _cli_client.check(r, verbose=_verbose(ctx))
        payload = r.json()
    _echo(payload, output_json)


@app.command("rm")
def remove_input(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    ref: str = typer.Argument(..., help="The input's ref, as `list` prints it"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Unmount an input. An uploaded file's bytes go with it."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/workflow/runs/{run_id}/inputs/{quote(ref, safe='')}")
        _cli_client.check(r, verbose=_verbose(ctx))
        payload = r.json()
    _echo(payload, output_json)

"""``coffer knowledge`` — the Knowledge page's collections, changes and uploads.

Spec knowledge "Manage knowledge in the web UI and on the command line". A
collection's pages and sources are plain files under the knowledge root, read,
edited and deleted with the reader's own tools; creating and describing a
collection, checking one, uploading sources, reading the changes feed and
undoing a delete are commands.
"""

from __future__ import annotations

from pathlib import Path

import typer

from coffer.surfaces.cli import _io
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli._route_command import Q, RouteCommand, mount
from coffer.surfaces.cli.groups import group
from coffer.surfaces.cli.registry import maps

K = {"uid": "knowledge"}
_UI = "Knowledge · "

SPECS = [
    RouteCommand(
        "knowledge collections",
        "GET",
        "/knowledge/collections",
        _UI + "collections",
        "Every collection with its description, page, source, waiting-source and finding counts.",
    ),
    RouteCommand(
        "knowledge create",
        "POST",
        "/knowledge/collections",
        _UI + "New collection",
        "Create a collection. Body: name, description.",
        body=True,
    ),
    RouteCommand(
        "knowledge describe",
        "PUT",
        "/knowledge/collections/{uid}/description",
        _UI + "edit a collection's description",
        "Rewrite a collection's description. Body: description.",
        names=K,
        body=True,
    ),
    RouteCommand(
        "knowledge check",
        "GET",
        "/knowledge/collections/{uid}/check",
        _UI + "a collection's Check",
        "A collection's mechanical findings: dead links, orphan pages, waiting sources.",
        names=K,
    ),
    RouteCommand(
        "knowledge tree",
        "GET",
        "/knowledge/tree",
        _UI + "the tree",
        "One level of the knowledge tree.",
        query=(Q("path", "A folder under the root"),),
    ),
    RouteCommand(
        "knowledge changes",
        "GET",
        "/knowledge/changes",
        _UI + "recent changes",
        "Recent changes across collections, newest first.",
        query=(Q("collection"), Q("limit", kind=int), Q("cursor")),
    ),
    RouteCommand(
        "knowledge restore",
        "POST",
        "/knowledge/changes/{version}/restore",
        _UI + "Undo a delete",
        "Restore what a delete removed (from the changes feed).",
    ),
    RouteCommand(
        "knowledge tidy-handoff",
        "GET",
        "/knowledge/tidy-handoff",
        _UI + "Tidy with an agent",
        "The prompt that hands tidying knowledge to an agent.",
    ),
]

mount(SPECS)

knowledge = group("knowledge")


@knowledge.command("upload")
@maps("knowledge upload", ("POST", "/knowledge/upload"), ui=_UI + "Upload")
def upload(
    collection: str = typer.Argument(..., help="The collection's folder name"),
    files: list[Path] = typer.Argument(..., help="Files to keep as sources"),
    as_json: bool = _io.json_option(),
) -> None:
    """Upload files into a collection; each is kept as a Markdown source."""
    results = []
    for path in files:
        try:
            data = path.expanduser().read_bytes()
        except OSError as e:
            _io.fail(
                "CLI_INVALID_INPUT",
                f"cannot read {path}: {e}",
                ExitCode.INVALID_INPUT,
                as_json=as_json,
            )
        results.append(
            _io.call(
                "POST",
                "/knowledge/upload",
                as_json=as_json,
                files={"file": (path.name, data)},
                form={"collection": collection},
            )
        )
    _io.emit(results, as_json=as_json)

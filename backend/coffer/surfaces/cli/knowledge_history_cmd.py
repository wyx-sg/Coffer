"""``coffer knowledge history | restore | changes | undo`` — a collection's
history from the terminal (spec knowledge "Keep every document's history and
undo a pass as a whole", "Follow knowledge changes across collections").

Registered onto the ``coffer knowledge`` group by ``knowledge_cmd``. Every
accepted write to a collection is a version naming who wrote it; these commands
read the versions, restore one, list the recent changes with the items still
waiting, and undo a curation pass as a whole.
"""

from __future__ import annotations

import json as _json
from collections.abc import Callable

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client


def register_history_commands(
    app: typer.Typer, *, console: Console, verbose: Callable[[typer.Context], bool]
) -> None:
    """Add the four history commands to ``app``."""
    _console = console
    _verbose = verbose

    def _who(change: dict[str, object]) -> str:
        writer = str(change["writer"])
        agent = change.get("agent")
        if writer == "curation":
            return f"curation ({agent}'s item)" if agent and agent != "user" else "curation"
        if writer == "agent" and agent:
            return str(agent)
        return {"user": "you", "disk": "edited on disk"}.get(writer, writer)

    @app.command("history")
    def history(
        ctx: typer.Context,
        path: str = typer.Argument(..., help="A document, e.g. shopee/infra/cache.md"),
        version: str = typer.Option("", "--version", help="Print this version's diff"),
        output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
    ) -> None:
        """List a document's versions, newest first, with who wrote each.

        \f
        Requirement "Keep every document's history and undo a pass as a whole".
        """
        c, _info = _cli_client.client_or_exit()
        with c:
            if version:
                r = c.get("/knowledge/history/diff", params={"path": path, "version": version})
            else:
                r = c.get("/knowledge/history", params={"path": path})
            _cli_client.check(r, verbose=_verbose(ctx))
        data = r.json()
        if output_json:
            typer.echo(_json.dumps(data, indent=2))
            return
        if version:
            typer.echo(data["diff"] or "(no textual change)")
            return
        table = Table(title=f"History of {path}")
        for column in ("version", "when", "written by", "what"):
            table.add_column(column)
        for entry in data["versions"]:
            change = entry["change"]
            table.add_row(change["version"][:10], change["time"], _who(change), change["summary"])
        _console.print(table)

    @app.command("restore")
    def restore(
        ctx: typer.Context,
        path: str = typer.Argument("", help="The document to restore"),
        version: str = typer.Argument("", help="The version to put back (from `history`)"),
        deleted: str = typer.Option(
            "",
            "--deleted",
            help="Bring back what this delete removed, a document or a whole collection "
            "(the delete's version, from `changes`)",
        ),
    ) -> None:
        """Put one version of a document back, as a new version — or, with
        `--deleted`, bring back a deleted document or collection.

        \f
        Requirement "Restore a deleted collection or document from Recent changes".
        """
        if bool(deleted) == bool(path and version):
            typer.echo("give PATH and VERSION, or --deleted VERSION", err=True)
            raise typer.Exit(2)
        c, _info = _cli_client.client_or_exit()
        with c:
            if deleted:
                r = c.post(f"/knowledge/changes/{deleted}/restore")
            else:
                r = c.post("/knowledge/history/restore", json={"path": path, "version": version})
            _cli_client.check(r, verbose=_verbose(ctx))
        if deleted:
            restored = ", ".join(d["path"] for d in r.json()["documents"])
            typer.echo(f"restored what {deleted[:10]} deleted: {restored}")
        else:
            typer.echo(f"restored {path} to {version[:10]}")

    @app.command("changes")
    def changes(
        ctx: typer.Context,
        version: str = typer.Argument(
            "", help="Show this change in full, with each document's diff"
        ),
        collection: str = typer.Option("", "--in", help="Only this collection"),
        limit: int = typer.Option(20, "--limit", help="How many changes"),
        output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
    ) -> None:
        """Recent changes to knowledge across collections, and the items waiting.

        \f
        Requirement "Follow knowledge changes across collections".
        """
        c, _info = _cli_client.client_or_exit()
        with c:
            if version:
                r = c.get(f"/knowledge/changes/{version}")
            else:
                params: dict[str, str | int] = {"limit": limit}
                if collection:
                    params["collection"] = collection
                r = c.get("/knowledge/changes", params=params)
            _cli_client.check(r, verbose=_verbose(ctx))
        data = r.json()
        if output_json:
            typer.echo(_json.dumps(data, indent=2))
            return
        if version:
            typer.echo(f"{data['change']['summary']} — {_who(data['change'])}")
            for diff in data["diffs"]:
                typer.echo(
                    f"\n{diff['status']} {diff['path']} (+{diff['added']} -{diff['removed']})"
                )
                typer.echo(diff["diff"])
            return
        table = Table(title="Recent changes")
        for column in ("version", "when", "collection", "by", "what", "documents"):
            table.add_column(column)
        for change in data["changes"]:
            docs = ", ".join(
                f"{d['path']} +{d['added']} -{d['removed']}" for d in change["documents"]
            )
            table.add_row(
                change["version"][:10],
                change["time"],
                ", ".join(change["collections"]),
                _who(change),
                change["summary"],
                docs,
            )
        _console.print(table)
        if data["waiting"]:
            typer.echo("waiting to be curated:")
            for item in data["waiting"]:
                typer.echo(f"  {item['path']} — {item['title']} (from {item['submitted_by']})")

    @app.command("undo")
    def undo(
        ctx: typer.Context,
        version: str = typer.Argument(..., help="The curation pass to undo (from `changes`)"),
    ) -> None:
        """Undo a curation pass as a whole: every document it wrote or retired
        goes back to how it was. Refused, naming the document, if one has changed
        since."""
        c, _info = _cli_client.client_or_exit()
        with c:
            r = c.post(f"/knowledge/changes/{version}/undo")
            _cli_client.check(r, verbose=_verbose(ctx))
        data = r.json()
        typer.echo(f"undid {version[:10]}: {len(data['documents'])} document(s) put back")

"""Print a command-line tool's interface for ``coffer cli show`` (spec
skill-manager "Serve required commands on REST, the command line and the web")."""

from __future__ import annotations

from typing import Any

import httpx
import typer

from coffer.surfaces.cli import _client as _cli_client

#: Reading a tool's help can take up to ~30 s on the daemon.
READ_TIMEOUT_SECONDS = 60.0


def fetch(c: httpx.Client, command: str, *, refresh: bool, verbose: bool) -> dict[str, Any]:
    """The interface of ``command``: what is kept, read first when nothing
    is (or when ``refresh``)."""
    path = f"/clis/{command}/interface"
    body: dict[str, Any] = {"status": "not_read"}
    if not refresh:
        r = c.get(path)
        _cli_client.check(r, verbose=verbose)
        body = r.json()
    if refresh or body["status"] == "not_read":
        typer.echo(f"reading {command} --help ...", err=True)
        r = c.post(path, timeout=READ_TIMEOUT_SECONDS)
        _cli_client.check(r, verbose=verbose)
        body = r.json()
    return body


def find_node(nodes: list[dict[str, Any]], path: list[str]) -> dict[str, Any] | None:
    return next((n for n in nodes if n["path"] == path), None)


def command_line(command: str, path: list[str]) -> str:
    return " ".join([command, *path])


def _row(left: str, right: str | None, width: int = 28) -> str:
    return f"  {left.ljust(width)}  {right or ''}".rstrip()


def print_tree(command: str, nodes: list[dict[str, Any]]) -> None:
    """Every command of the tool, one per line, indented by depth, with its
    one-line summary from its parent's list."""
    summaries = {(*n["path"], s["name"]): s["summary"] for n in nodes for s in n["subcommands"]}
    for n in nodes:
        summary = summaries.get(tuple(n["path"])) or n["description"] or ""
        indent = "  " * len(n["path"])
        typer.echo(
            f"{indent}{command_line(command, n['path'])}" + (f"  — {summary}" if summary else "")
        )


def print_node(command: str, node: dict[str, Any]) -> None:
    typer.echo("")
    typer.echo(f"{command_line(command, node['path'])}")
    if node["description"]:
        typer.echo(f"  {node['description']}")
    if node["usage"]:
        typer.echo(f"usage: {node['usage']}")
    if node["error"]:
        typer.echo(f"no help: {node['error']}")
    if not node["structured"] and node["raw"]:
        typer.echo(node["raw"].rstrip())
        return
    if node["subcommands"]:
        typer.echo("commands:")
        for s in node["subcommands"]:
            typer.echo(_row(s["name"], s["summary"]))
    if node["arguments"]:
        typer.echo("arguments:")
        for a in node["arguments"]:
            typer.echo(_row(a["name"] + (" (required)" if a["required"] else ""), a["description"]))
    if node["options"]:
        typer.echo("options:")
        for o in node["options"]:
            names = ", ".join(o["names"]) + (f" {o['metavar']}" if o["metavar"] else "")
            tail = [o["description"] or ""]
            if o["default"]:
                tail.append(f"[default: {o['default']}]")
            if o["required"]:
                tail.append("[required]")
            typer.echo(_row(names, " ".join(t for t in tail if t)))


__all__ = ["READ_TIMEOUT_SECONDS", "command_line", "fetch", "find_node", "print_node", "print_tree"]

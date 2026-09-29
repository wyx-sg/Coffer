"""``coffer scan --ref`` — one scanned row in full.

A scan row is a summary; its detail is the read the web UI's page for that row
makes (spec agent-registry "Show one direct MCP entry's full configuration
without its secrets", spec skill-manager "Preview an unmanaged skill
read-only"). Secret values never reach this module: the daemon withholds them.
"""

from __future__ import annotations

import json as _json
from typing import Any

import httpx
import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._options import ExitCode


def detail(
    c: httpx.Client, row: dict[str, Any], *, source: str | None, verbose: bool
) -> dict[str, Any]:
    """The full read behind ``row``: the row itself for a detected agent."""
    if row["kind"] == "mcp":
        params = {"source": source} if source is not None else None
        r = c.get(f"/agents/{row['agent_uid']}/mcp-entries/{row['name']}", params=params)
    elif row["kind"] == "skill":
        r = c.get(
            f"/agents/{row['agent_uid']}/unmanaged-skills/{row['name']}",
            params={"location": row["location"]},
        )
    else:
        return row
    if r.status_code == 404:
        typer.echo(f"{row['ref']!r} names nothing to show any more — run: coffer scan", err=True)
        raise typer.Exit(int(ExitCode.NOT_FOUND))
    _cli_client.check(r, verbose=verbose)
    body: dict[str, Any] = r.json()
    return body


def _mcp_lines(d: dict[str, Any]) -> list[tuple[str, str]]:
    secret = set(d.get("secret_keys") or [])
    rows: list[tuple[str, str]] = [("name", d["name"]), ("file", d["path"])]
    rows.append(("transport", d["transport"]))
    if d["transport"] == "stdio":
        rows.append(("command", " ".join([d.get("command") or "", *d.get("args", [])]).strip()))
    else:
        rows.append(("url", d.get("url") or ""))
    rows += [("cwd", d["cwd"])] if d.get("cwd") else []
    rows += [(f"env {k}", "(secret)" if k in secret else "(set)") for k in d.get("env_keys", [])]
    rows += [
        (f"header {k}", "(secret)" if k in secret else "(set)") for k in d.get("header_keys", [])
    ]
    rows += [(f["key"], "(secret)" if f["masked"] else str(f["value"])) for f in d.get("extra", [])]
    return rows


def echo(kind: str, d: dict[str, Any], *, output_json: bool) -> None:
    """Print ``d`` as JSON, or as one ``label: value`` line per field."""
    if output_json:
        typer.echo(_json.dumps(d, indent=2))
        return
    if kind == "mcp":
        lines = _mcp_lines(d)
    else:
        lines = [(k, "" if v is None else str(v)) for k, v in d.items() if not isinstance(v, dict)]
    for label, value in lines:
        typer.echo(f"{label}: {value}")

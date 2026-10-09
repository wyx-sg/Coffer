"""``coffer mcp test`` — the one MCP command left on the command line.

The MCP install hand-off asks an agent to verify the server answers, and the
agent runs this. Registering, editing and removing servers is the MCP servers
page's job (spec resource-framework "Offer every management operation on the command line").

A server is named by its NAME; the uid the daemon addresses it by is looked up
once through ``_resolve`` (ADR identity-is-the-uid-inside-the-file).
"""

from __future__ import annotations

import shlex

import httpx
import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import _io
from coffer.surfaces.cli._resolve import resolve_uid

app = typer.Typer(help="Check an MCP server")


def _error_message(r: httpx.Response) -> str:
    try:
        return str(r.json()["error"]["message"])
    except Exception:
        return f"HTTP {r.status_code}"


def _capabilities(r: httpx.Response) -> dict[str, object]:
    """What the refresh found, as counts — or why it found nothing."""
    if r.status_code != 200:
        return {"error": _error_message(r)}
    data = r.json()
    counts: dict[str, object] = {
        plural: len(data.get(plural) or []) for plural in ("tools", "prompts", "resources")
    }
    return {**counts, "from_cache": bool(data.get("from_cache"))}


def _capabilities_line(r: httpx.Response) -> str:
    if r.status_code != 200:
        return f"capabilities: not re-queried ({_error_message(r)})"
    data = r.json()
    counts = ", ".join(
        f"{len(data.get(plural) or [])} {plural}" for plural in ("tools", "prompts", "resources")
    )
    if data.get("from_cache"):
        return f"capabilities: {counts} (last known — the upstream did not answer)"
    return f"capabilities: {counts} (re-queried)"


@app.command("test")
def test_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Server name"),
    prompt: bool = typer.Option(
        False, "--prompt", help="On a failure, also print the prompt to give your agent"
    ),
    as_json: bool = _io.json_option(),
) -> None:
    """Re-query a server's capabilities, then report whether it answers.

    Exits 7 when the server does not answer. With ``--prompt``, a failure also
    prints the hand-off prompt the server's page offers for it: installing a
    launcher that is not found here, or finding why the server fails.
    ``--json`` prints the test's answer (``ok``, ``latency_ms``,
    ``error_message``, ``handoff``) with the refresh's counts under
    ``capabilities``; a failed test still exits 7.

    \f
    Routes: ``POST /resources/mcp_server/{uid}/refresh`` then ``.../test``
    (spec mcp-gateway "Manage MCP servers as resources"). The refresh's own
    failure is reported, not fatal: an unreachable upstream is exactly what the
    health test that follows is there to name.
    """
    verbose = bool((ctx.obj or {}).get("verbose", False))
    with _io.client(as_json=as_json) as c:
        uid = resolve_uid(c, "mcp_server", name, verbose=verbose, as_json=as_json)
        refreshed = c.post(f"/resources/mcp_server/{uid}/refresh")
        if refreshed.status_code == 404:
            _cli_client.check(refreshed, verbose=verbose, as_json=as_json)
        r = c.post(f"/resources/mcp_server/{uid}/test")
        _cli_client.check(r, verbose=verbose, as_json=as_json)
    data = r.json()
    if as_json:
        _io.emit({**data, "capabilities": _capabilities(refreshed)}, as_json=True)
        if not data["ok"]:
            raise typer.Exit(7)
        return
    typer.echo(_capabilities_line(refreshed))
    if data["ok"]:
        typer.echo(f"OK  ({data['latency_ms']} ms)")
    else:
        typer.echo(f"FAIL ({data['latency_ms']} ms): {data.get('error_message')}", err=True)
        handoff = data.get("handoff")
        if handoff and prompt:
            typer.echo(handoff["prompt"])
        elif handoff:
            typer.echo(
                f"hand off: coffer mcp test {shlex.quote(name)} --prompt"
                "  (a prompt for your agent)",
                err=True,
            )
        raise typer.Exit(7)

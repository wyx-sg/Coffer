"""``coffer tool …`` — custom-tool groups: HTTP APIs whose requests are tools.

Spec mcp-gateway "Manage custom tools on REST and the command line"; design
add-http-custom-tools §9. A group is an ``mcp_server`` of the ``http_api``
transport, addressed by its fixed name, which prefixes every tool an agent sees
(``<group>__<tool>``). ``enable``, ``disable`` and ``scope`` are the shared
lifecycle verbs of that kind; one tool is managed with ``coffer tool op``.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._approvals import WAIT_OPTION, pending_for, settle
from coffer.surfaces.cli._kind_verbs import KindVerbs, _agent_uids, register_kind_verbs, verbose_of
from coffer.surfaces.cli._tool_common import get_group, pairs, print_group
from coffer.surfaces.cli.tool_op_cmd import op_app

app = typer.Typer(help="Manage custom tools: HTTP API requests your agents call as tools")


def _read_openapi(c: Any, source: str, *, verbose: bool) -> dict[str, Any]:
    if source.startswith(("http://", "https://")):
        body: dict[str, Any] = {"url": source}
    else:
        path = pathlib.Path(source).expanduser()
        if not path.is_file():
            typer.echo(f"no such file: {source}", err=True)
            raise typer.Exit(2)
        body = {"document": path.read_text(encoding="utf-8"), "filename": path.name}
    r = c.post("/custom-tools/openapi", json=body)
    _cli_client.check(r, verbose=verbose)
    reading: dict[str, Any] = r.json()
    for warning in reading.get("warnings", []):
        typer.echo(f"warning: {warning}", err=True)
    return reading


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List every custom-tool group, failing ones first."""
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/custom-tools")
        _cli_client.check(r, verbose=verbose)
    groups = r.json()["groups"]
    if output_json:
        typer.echo(json.dumps({"groups": groups}, indent=2))
        return
    if not groups:
        typer.echo("no custom-tool groups")
        return
    for g in groups:
        on = sum(1 for t in g["tools"] if t["enabled"])
        typer.echo(
            f"{g['name']:<24} {g['health']:<10} {on}/{len(g['tools'])} tools  {g['base_url']}"
        )


@app.command("show")
def show_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Group name"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Show one group: its definition, its last 24 hours and its tools."""
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        group = get_group(c, name, verbose=verbose)
    if output_json:
        typer.echo(json.dumps(group, indent=2))
        return
    print_group(group)


@app.command("add")
def add_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Group name (the agents' prefix; fixed, ≤24 chars)"),
    base_url: str | None = typer.Option(
        None, "--base-url", help="Every tool's path is added to it"
    ),
    description: str | None = typer.Option(None, "--description"),
    header: list[str] = typer.Option([], "--header", help="Static header KEY=VALUE (repeatable)"),  # noqa: B008
    auth_header: str | None = typer.Option(None, "--auth-header", help="e.g. Authorization"),
    auth_prefix: str | None = typer.Option(None, "--auth-prefix", help='e.g. "Bearer "'),
    secret: str | None = typer.Option(
        None, "--secret", help="Secrets-page name for the auth header"
    ),
    timeout: int = typer.Option(30, "--timeout", help="Per-request timeout in seconds (1-300)"),
    agents: str | None = typer.Option(None, "--agents", help="Only these agents (a,b)"),
    openapi: str | None = typer.Option(
        None, "--openapi", help="Import from an OpenAPI URL or file"
    ),
    operation: list[str] = typer.Option(  # noqa: B008
        [],
        "--operation",
        help='With --openapi: an operation to import, as "POST /refunds" (repeatable)',
    ),
    all_operations: bool = typer.Option(False, "--all-operations", help="Import every operation"),
    wait: bool = WAIT_OPTION,
) -> None:
    """Create a group, empty or imported from an OpenAPI document.

    With --openapi and no --operation, the GET operations are imported. Binding
    a stored secret waits for approval in the Coffer app; the command says so
    and exits 9, or waits with --wait.
    """
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        tools: list[dict[str, Any]] = []
        source: dict[str, Any] | None = None
        if openapi is not None:
            reading = _read_openapi(c, openapi, verbose=verbose)
            ops = reading["operations"]
            keys = {op["key"] for op in ops}
            unknown = sorted(set(operation) - keys)
            if unknown:
                typer.echo(f"no such operation(s): {', '.join(unknown)}", err=True)
                raise typer.Exit(6)
            chosen = [
                op
                for op in ops
                if all_operations
                or (op["key"] in operation if operation else op["tool"]["method"] == "GET")
            ]
            tools = [op["tool"] for op in chosen]
            source = {
                "kind": reading["source_kind"],
                "location": reading["location"],
                "title": reading["title"],
                "version": reading["version"],
                "skipped": sorted(keys - {op["key"] for op in chosen}),
            }
            base_url = base_url or reading.get("base_url")
            if secret and auth_header is None and reading.get("auth_header"):
                auth_header = reading["auth_header"]
                auth_prefix = reading.get("auth_prefix", "") if auth_prefix is None else auth_prefix
        if not base_url:
            typer.echo("--base-url is required (the document names no server)", err=True)
            raise typer.Exit(2)
        if secret and not auth_header:
            auth_header = "Authorization"
        payload: dict[str, Any] = {
            "name": name,
            "description": description,
            "base_url": base_url,
            "headers": pairs("--header", header),
            "auth": (
                {"header": auth_header, "prefix": auth_prefix or "", "secret": secret}
                if auth_header
                else None
            ),
            "timeout_seconds": timeout,
            "tools": tools,
            "source": source,
        }
        if agents is not None:
            names = [n.strip() for n in agents.split(",") if n.strip()]
            payload["agents"] = _agent_uids(c, names, verbose=verbose)
        r = c.post("/custom-tools", json=payload)
        _cli_client.check(r, verbose=verbose)
        group = r.json()
        typer.echo(f"created: custom-tool group {name} with {len(group['tools'])} tools")
        settle(c, pending_for(c, group["uid"], verbose=verbose), wait=wait, verbose=verbose)


@app.command("edit")
def edit_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Group name"),
    description: str | None = typer.Option(None, "--description"),
    base_url: str | None = typer.Option(None, "--base-url"),
    header: list[str] = typer.Option([], "--header", help="Static header KEY=VALUE (repeatable)"),  # noqa: B008
    clear_headers: bool = typer.Option(
        False, "--clear-headers", help="Drop every static header first"
    ),
    auth_header: str | None = typer.Option(None, "--auth-header"),
    auth_prefix: str | None = typer.Option(None, "--auth-prefix"),
    secret: str | None = typer.Option(
        None, "--secret", help="Secrets-page name for the auth header"
    ),
    clear_auth: bool = typer.Option(False, "--clear-auth", help="Remove the auth header"),
    timeout: int | None = typer.Option(None, "--timeout", help="Per-request timeout (1-300)"),
    wait: bool = WAIT_OPTION,
) -> None:
    """Change a group's description, base URL, headers, auth or timeout (its name is fixed).

    Moving the base URL or binding another secret waits for approval in the
    Coffer app before the secret is sent there.
    """
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        body: dict[str, Any] = {}
        if description is not None:
            body["description"] = description
        if base_url is not None:
            body["base_url"] = base_url
        if timeout is not None:
            body["timeout_seconds"] = timeout
        if header or clear_headers:
            current = {} if clear_headers else get_group(c, name, verbose=verbose)["headers"]
            body["headers"] = {**current, **pairs("--header", header)}
        if clear_auth:
            body["auth"] = None
        elif auth_header is not None or auth_prefix is not None or secret is not None:
            now = get_group(c, name, verbose=verbose).get("auth") or {}
            body["auth"] = {
                "header": auth_header or now.get("header") or "Authorization",
                "prefix": now.get("prefix", "") if auth_prefix is None else auth_prefix,
                "secret": secret if secret is not None else now.get("secret"),
            }
        if not body:
            typer.echo("nothing to change", err=True)
            raise typer.Exit(2)
        r = c.patch(f"/custom-tools/{name}", json=body)
        _cli_client.check(r, verbose=verbose)
        typer.echo(f"updated: custom-tool group {name}")
        settle(c, pending_for(c, r.json()["uid"], verbose=verbose), wait=wait, verbose=verbose)


@app.command("rm")
def rm_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Group name"),
    yes: bool = typer.Option(False, "--yes", "-y", "--force", "-f", help="Do not ask"),
) -> None:
    """Remove a group and all its tools. The bound secret stays on the Secrets page."""
    verbose = verbose_of(ctx)
    if not yes and not typer.confirm(f"Remove custom-tool group {name!r} and its tools?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/custom-tools/{name}")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed: custom-tool group {name}")


@app.command("reimport")
def reimport_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Group name"),
    file: str | None = typer.Option(None, "--file", help="The document again (a file import)"),
    add: list[str] = typer.Option(  # noqa: B008
        [], "--add", help='An added operation to import, as "POST /refunds"'
    ),
    add_all: bool = typer.Option(False, "--add-all", help="Import every added operation"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Apply without asking"),
    output_json: bool = typer.Option(False, "--json", help="Print the preview as JSON and stop"),
) -> None:
    """Read the group's OpenAPI source again: preview what it adds and removes, then apply.

    Kept tools keep their switch, changes-data flag and reach override.
    """
    verbose = verbose_of(ctx)
    body: dict[str, Any] = {}
    if file is not None:
        body["document"] = pathlib.Path(file).expanduser().read_text(encoding="utf-8")
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/custom-tools/{name}/reimport/preview", json=body)
        _cli_client.check(r, verbose=verbose)
        preview = r.json()
        if output_json:
            typer.echo(json.dumps(preview, indent=2))
            return
        added = [op["key"] for op in preview["added"]]
        for key in added:
            typer.echo(f"+ {key}")
        for tool in preview["removed"]:
            typer.echo(f"- {tool}")
        typer.echo(f"  {len(preview['kept'])} kept")
        if not added and not preview["removed"]:
            typer.echo("up to date; applying refreshes the kept tools' requests")
        chosen = added if add_all else [k for k in add if k in added]
        if not yes and not typer.confirm("Apply this re-import?"):
            raise typer.Exit(1)
        r = c.post(f"/custom-tools/{name}/reimport", json={**body, "add": chosen})
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"re-imported: {len(chosen)} added, {len(preview['removed'])} removed")


register_kind_verbs(
    app,
    KindVerbs(
        kind="mcp_server",
        noun="custom-tool group",
        verbs=frozenset({"enable", "disable", "scope"}),
        name_fixed=True,
        titled=False,
        help={
            "enable": "Switch a custom-tool group on.",
            "disable": "Switch a custom-tool group off: agents see none of its tools.",
            "scope": "Show or set which agents a group reaches (this machine only).",
        },
    ),
)

app.add_typer(op_app, name="op")

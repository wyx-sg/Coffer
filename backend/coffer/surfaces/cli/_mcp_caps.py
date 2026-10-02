"""``coffer mcp cap list|enable|disable`` — one server's tools, prompts and resources.

A capability is named on the command line by a typed ref — ``tool:<name>``,
``prompt:<name>`` or ``resource:<uri>`` — so one command toggles any mix of
them (spec mcp-gateway "Toggle individual capabilities"). Every ref is checked
against what the server offers BEFORE anything is toggled: a ref that names
nothing refuses the whole command with nothing changed.

``cap list`` flags a tool whose client-visible name
(``mcp__coffer__<server>__<tool>``) is longer than the 64 characters model
provider APIs accept (spec mcp-gateway "Flag tools whose client-visible name is
too long"). The flag only informs: the tool stays enabled and listed.

Like the rest of ``coffer mcp``, these take the server's NAME and resolve it to a
uid once per command (ADR identity-is-the-uid-inside-the-file).
"""

from __future__ import annotations

import json as _json
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import verbose_of
from coffer.surfaces.cli._resolve import resolve_uid

_console = Console()

cap_app = typer.Typer(help="List and toggle a server's tools, prompts and resources")

#: type → (the capabilities read's list key, the field that holds the key a ref names)
_TYPES: dict[str, tuple[str, str]] = {
    "tool": ("tools", "original_name"),
    "prompt": ("prompts", "original_name"),
    "resource": ("resources", "original_uri"),
}
#: Model provider APIs refuse a tool name longer than this.
CLIENT_NAME_LIMIT = 64
#: Some clients (Cursor) silently drop a tool whose name is longer than this.
CLIENT_DROP_LIMIT = 60


def _too_long(row: dict[str, Any]) -> bool | None:
    """Over the provider limit; ``None`` for a row type with no client-visible name."""
    length = row.get("client_name_length")
    return None if length is None else int(length) > CLIENT_NAME_LIMIT


def _warning(length: int) -> str:
    return (
        f"client-visible name is {length} characters, over the {CLIENT_NAME_LIMIT} "
        f"model provider APIs accept; some clients drop names above {CLIENT_DROP_LIMIT}"
    )


def _read(c: httpx.Client, uid: str, *, verbose: bool) -> dict[str, Any]:
    r = c.get(f"/resources/mcp_server/{uid}/capabilities")
    _cli_client.check(r, verbose=verbose)
    return r.json()  # type: ignore[no-any-return]


def _parse_ref(ref: str) -> tuple[str, str]:
    type_, sep, key = ref.partition(":")
    if not sep or type_ not in _TYPES or not key:
        typer.echo(
            f"a capability ref is tool:<name>, prompt:<name> or resource:<uri>, got {ref!r}",
            err=True,
        )
        raise typer.Exit(2)
    return type_, key


def _check_type(type_: str | None) -> list[str]:
    if type_ is None:
        return list(_TYPES)
    if type_ not in _TYPES:
        typer.echo(f"--type is one of {', '.join(_TYPES)}, got {type_!r}", err=True)
        raise typer.Exit(2)
    return [type_]


@cap_app.command("list")
def cap_list(
    ctx: typer.Context,
    server: str = typer.Argument(..., help="Server name"),
    type_: str | None = typer.Option(None, "--type", help="tool | prompt | resource"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List a server's capabilities, each with the ref that toggles it.

    A tool whose client-visible name (mcp__coffer__<server>__<tool>) is over 64
    characters is flagged; it stays enabled and listed.
    """
    verbose = verbose_of(ctx)
    types = _check_type(type_)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "mcp_server", server, verbose=verbose)
        caps = _read(c, uid, verbose=verbose)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for t in types:
        plural, key_field = _TYPES[t]
        rows = []
        for item in caps.get(plural) or []:
            row = {**item, "ref": f"{t}:{item[key_field]}"}
            if t != "resource":
                row["name_too_long"] = _too_long(item)
                if row["name_too_long"]:
                    row["warning"] = _warning(int(item["client_name_length"]))
            rows.append(row)
        grouped[plural] = rows
    if output_json:
        typer.echo(_json.dumps(grouped, indent=2))
        return
    _render(server, grouped)


def _render(server: str, grouped: dict[str, list[dict[str, Any]]]) -> None:
    table = Table(title=f"{server} capabilities")
    for col in ("Ref", "Enabled", "Name length", "Description"):
        table.add_column(col)
    flagged = 0
    for rows in grouped.values():
        for row in rows:
            length = row.get("client_name_length")
            shown = "—" if length is None else str(length)
            if row.get("name_too_long"):
                flagged += 1
                shown += " !"
            table.add_row(
                row["ref"],
                "yes" if row["enabled"] else "no",
                shown,
                (row.get("description") or "")[:60],
            )
    _console.print(table)
    if flagged:
        typer.echo(
            f"! {flagged} with a client-visible name (mcp__coffer__{server}__<name>) over "
            f"{CLIENT_NAME_LIMIT} characters: model provider APIs refuse such a name, and "
            f"some clients drop names above {CLIENT_DROP_LIMIT}."
        )


def _toggle(ctx: typer.Context, server: str, refs: list[str], *, enable: bool) -> None:
    verbose = verbose_of(ctx)
    op = "enable" if enable else "disable"
    parsed = [_parse_ref(ref) for ref in refs]
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "mcp_server", server, verbose=verbose)
        caps = _read(c, uid, verbose=verbose)
        offered = {
            (t, item[key_field])
            for t, (plural, key_field) in _TYPES.items()
            for item in caps.get(plural) or []
        }
        missing = [f"{t}:{key}" for t, key in parsed if (t, key) not in offered]
        if missing:
            typer.echo(f"{server} offers no {', '.join(missing)} — nothing changed", err=True)
            raise typer.Exit(4)
        for t, key in parsed:
            # The key travels in the body: a resource key is a URI with '/' in it.
            r = c.post(
                f"/resources/mcp_server/{uid}/capabilities/{t}/{op}",
                json={"capability_key": key},
            )
            if r.status_code == 404:
                typer.echo(f"capability not found: {t}:{key} on {server}", err=True)
                raise typer.Exit(4)
            _cli_client.check(r, verbose=verbose)
            typer.echo(f"{op}d: {server} {t}:{key}")


_REFS = typer.Argument(..., metavar="REF...", help="tool:<name> | prompt:<name> | resource:<uri>")


@cap_app.command("enable")
def cap_enable(
    ctx: typer.Context,
    server: str = typer.Argument(..., help="Server name"),
    refs: list[str] = _REFS,
) -> None:
    """Enable capabilities, each named by a typed ref."""
    _toggle(ctx, server, refs, enable=True)


@cap_app.command("disable")
def cap_disable(
    ctx: typer.Context,
    server: str = typer.Argument(..., help="Server name"),
    refs: list[str] = _REFS,
) -> None:
    """Disable capabilities, each named by a typed ref."""
    _toggle(ctx, server, refs, enable=False)

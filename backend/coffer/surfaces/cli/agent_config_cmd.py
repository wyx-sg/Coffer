"""coffer agent config ls/cat/edit — the agent's own curated config files.

The whole-file half of ``coffer agent config``: list the files the agent's type
declares, print one, and edit one through ``$EDITOR``. The directory-entry half
(``config files/write/rm``, which addresses a child file inside one of those
entries) lives in ``agent_workspace_cmd.py``, and both attach onto the same
``config_app`` typer that ``agent_cmd`` owns — the user-facing tree stays
``coffer agent config ...`` whichever module a command is written in.

Its own module for the same reason as its siblings: the backend 400-line file
cap. Like every command in the agent tree it takes the agent's NAME and resolves
it once, through ``_resolve``, to the uid the routes address
(ADR resource-identity-is-an-immutable-uid).
"""

from __future__ import annotations

import json as _json
from typing import Any

import click
import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


# Exit 4 on a 404 about the config KEY — the agent was already resolved (and a
# bad name already reported) by ``resolve_uid``.
def _not_found_exit(r: Any) -> None:
    if r.status_code == 404:
        typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
        raise typer.Exit(4)


def config_ls(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List an agent's curated config files."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "agent", name, verbose=verbose)
        r = c.get(f"/agents/{uid}/config-files")
        _cli_client.check(r, verbose=verbose)
    items = r.json()["items"]
    if output_json:
        typer.echo(_json.dumps(items, indent=2))
        return
    table = Table(title=f"Config files — {name}")
    for col in ("Key", "Format", "Path", "Exists"):
        table.add_column(col)
    for it in items:
        table.add_row(it["key"], it["format"], it["path"], "✓" if it["exists"] else "")
    _console.print(table)


def config_cat(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    key: str = typer.Argument(..., help="Config-file key (e.g. settings, config, instructions)"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Print one config file's content (--json: the whole read, fingerprint included)."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "agent", name, verbose=verbose)
        r = c.get(f"/agents/{uid}/config-files/{key}")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    if output_json:
        typer.echo(_json.dumps(r.json(), indent=2))
        return
    typer.echo(r.json()["content"], nl=False)


def config_edit(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    key: str = typer.Argument(..., help="Config-file key (e.g. settings, config, instructions)"),
    from_file: str | None = typer.Option(
        None,
        "--from-file",
        help="Read the new content from PATH instead of opening $EDITOR (non-interactive).",
    ),
) -> None:
    """Edit one config file. Opens $EDITOR on its current content, or use --from-file.

    On save, Coffer validates the content against the file's format (malformed
    JSON/TOML is rejected and the on-disk file is left unchanged), writes it
    atomically, and keeps a `<path>.bak` of the prior version. The write carries
    the fingerprint of the content it started from, so a change made on disk in
    the meantime is refused (exit 5) instead of overwritten (spec agent-registry
    "Reject stale config-file writes by fingerprint").
    """
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "agent", name, verbose=verbose)
        # Fetch current content (an unknown key still exits 4 here).
        r = c.get(f"/agents/{uid}/config-files/{key}")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
        current = r.json()["content"]
        fingerprint = r.json()["fingerprint"]

        if from_file is not None:
            import pathlib

            try:
                content = pathlib.Path(from_file).read_text(encoding="utf-8")
            except OSError as e:
                typer.echo(f"cannot read {from_file}: {e}", err=True)
                raise typer.Exit(1) from e
        else:
            # click.edit (typer has no `edit`): opens $EDITOR with the current
            # content; returns None if the user made no changes / aborted.
            edited = click.edit(current, extension=f".{key}")
            if edited is None:
                typer.echo("no changes", err=True)
                raise typer.Exit(0)
            content = edited

        w = c.put(
            f"/agents/{uid}/config-files/{key}",
            json={"content": content, "expected_fingerprint": fingerprint},
        )
        _not_found_exit(w)
        if w.status_code == 409:
            typer.echo(w.json().get("error", {}).get("message", "file changed"), err=True)
            typer.echo(f"hint: re-run `coffer agent config edit {name} {key}`", err=True)
            raise typer.Exit(5)
        if w.status_code == 422:
            typer.echo(w.json().get("error", {}).get("message", "invalid content"), err=True)
            raise typer.Exit(2)
        _cli_client.check(w, verbose=verbose)
    typer.echo(f"saved: {key} (a .bak was kept)")


def attach(config_app: typer.Typer) -> None:
    """Register the whole-file config commands on agent_cmd's ``config`` typer."""
    config_app.command("ls")(config_ls)
    config_app.command("cat")(config_cat)
    config_app.command("edit")(config_edit)

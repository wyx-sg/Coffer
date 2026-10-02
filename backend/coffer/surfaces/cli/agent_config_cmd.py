"""``coffer agent config edit|rm`` — write and delete an agent's own config files.

Reading them is not a command: ``coffer path agent <name> config`` names the
files, and they are read on disk (spec agent-registry "Expose every agent
operation through REST, CLI and the Agents page"). What stays here are the
writes, because a write is validated, backed up and audited by the daemon:

- ``edit <name> <key>`` rewrites a whole config file;
- ``edit <name> <key>/<child>`` writes one child file of a directory entry,
  creating it when it does not exist yet;
- ``rm <name> <key>/<child>`` deletes one child file.

Every edit sends the fingerprint of the read it started from, so a change made
on disk in the meantime is refused, not overwritten (spec agent-registry "Reject
stale config-file writes by fingerprint").

Its own module for the backend 400-line file cap; ``agent_cmd`` calls
:func:`attach`. Like every command in the agent tree it takes the agent's NAME
and resolves it once to the uid the routes address
(ADR identity-is-the-uid-inside-the-file).
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

import click
import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import verbose_of
from coffer.surfaces.cli._resolve import resolve_ref

config_app = typer.Typer(
    help="Write and delete an agent's config files (read them via `coffer path`)"
)

_TARGET_HELP = (
    "Config-file key (e.g. settings, config, instructions), or KEY/CHILD for one "
    "file inside a directory entry (e.g. subagents/reviewer.md)"
)


# Exit 4 on a 404 about the config KEY — the agent was already resolved (and a
# bad name already reported) by the resolve.
def _not_found_exit(r: Any) -> None:
    if r.status_code == 404:
        typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
        raise typer.Exit(4)


def _route(uid: str, target: str) -> tuple[str, bool]:
    """The route ``target`` names, and whether it is a directory child."""
    key, sep, child = target.partition("/")
    if not key or (sep and not child):
        typer.echo(f"expected KEY or KEY/CHILD, got {target!r}", err=True)
        raise typer.Exit(2)
    if child:
        return f"/agents/{uid}/config-files/{key}/files/{child}", True
    return f"/agents/{uid}/config-files/{key}", False


def _read_source(from_file: str) -> str:
    if from_file == "-":
        return sys.stdin.read()
    try:
        return pathlib.Path(from_file).read_text(encoding="utf-8")
    except OSError as e:
        typer.echo(f"cannot read {from_file}: {e}", err=True)
        raise typer.Exit(1) from e


def config_edit(
    ctx: typer.Context,
    name: str = typer.Argument(..., metavar="NAME", help="Agent name or uid"),
    target: str = typer.Argument(..., metavar="KEY[/CHILD]", help=_TARGET_HELP),
    from_file: str | None = typer.Option(
        None,
        "--from-file",
        help="Take the new content from PATH ('-' for stdin) instead of opening $EDITOR.",
    ),
) -> None:
    """Edit one config file, or one file inside a directory entry.

    Opens $EDITOR on the current content, or takes it from --from-file. Coffer
    validates the content against the file's format (malformed JSON/TOML is
    rejected, exit 2, and the file is left unchanged), writes it atomically and
    keeps a `<path>.bak` of the prior version. A change made on disk since the
    read is refused (exit 5) instead of overwritten.

    \f
    Spec agent-registry "Reject stale config-file writes by fingerprint": the
    PUT always carries the fingerprint of the GET it started from — with
    --from-file too, so a scripted write cannot clobber a concurrent one.
    """
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_ref(c, "agent", name, verbose=verbose)["uid"]
        route, is_child = _route(uid, target)
        r = c.get(route)
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
        current, fingerprint = r.json()["content"], r.json()["fingerprint"]

        if from_file is not None:
            content = _read_source(from_file)
        else:
            # click.edit (typer has no `edit`): opens $EDITOR on the current
            # content; returns None if the user made no changes / aborted.
            suffix = ".md" if is_child else f".{target}"
            edited = click.edit(current, extension=suffix)
            if edited is None:
                typer.echo("no changes", err=True)
                raise typer.Exit(0)
            content = edited

        w = c.put(route, json={"content": content, "expected_fingerprint": fingerprint})
        _not_found_exit(w)
        if w.status_code == 409:
            typer.echo(w.json().get("error", {}).get("message", "file changed"), err=True)
            typer.echo(f"hint: re-run `coffer agent config edit {name} {target}`", err=True)
            raise typer.Exit(5)
        if w.status_code == 422:
            typer.echo(w.json().get("error", {}).get("message", "invalid content"), err=True)
            raise typer.Exit(2)
        _cli_client.check(w, verbose=verbose)
    typer.echo(f"saved: {target} (a .bak was kept)")


def config_rm(
    ctx: typer.Context,
    name: str = typer.Argument(..., metavar="NAME", help="Agent name or uid"),
    target: str = typer.Argument(
        ..., metavar="KEY/CHILD", help="One file inside a directory entry (e.g. subagents/x.md)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", "--force", "-f", help="Do not ask"),
) -> None:
    """Delete one file inside a directory entry (its content is kept as .bak)."""
    if "/" not in target:
        typer.echo("only a file inside a directory entry can be removed: KEY/CHILD", err=True)
        raise typer.Exit(2)
    if not yes and not typer.confirm(f"Really delete {target} of agent {name}?"):
        raise typer.Exit(1)
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_ref(c, "agent", name, verbose=verbose)["uid"]
        route, _is_child = _route(uid, target)
        r = c.delete(route)
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed: {target}")


def attach(agent_app: typer.Typer) -> None:
    """Register ``coffer agent config edit|rm`` on agent_cmd's typer."""
    config_app.command("edit")(config_edit)
    config_app.command("rm")(config_rm)
    agent_app.add_typer(config_app, name="config")

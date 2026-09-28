"""``coffer skill …`` — managed skills (spec skill-manager "Cover skill
management on REST, the CLI and the web").

``edit``, ``rm``, ``enable``, ``disable`` and ``scope`` are the lifecycle verbs
every kind shares (``_kind_verbs``). ``list`` and ``show`` are the skill's own,
because they read ``/skills``, which carries what the generic resource
document does not — the source, the version hash, the master folder and the
per-agent deliveries. ``add`` takes a folder, because importing one is how a
skill comes to exist. ``verify`` reports drift.

A skill's name is fixed once registered (spec skill-manager "Register each
skill as a resource with a SKILL.md-safe name"): ``edit --name`` is kept so the
daemon's ``NAME_IMMUTABLE`` refusal can say what a new name costs, and
``--title`` is the label to change instead. A skill's master folder is plain
files: ``coffer path skill <name>`` names it and it is edited on disk, so this
group has no command that lists, prints or writes a file in it. Unmanaged
skill folders are rows of ``coffer scan``, acted on by ``coffer adopt`` and
``coffer discard``.

Every command takes a name (or a uid) and resolves it once through
``_resolve`` (ADR resource-identity-is-an-immutable-uid).
"""

from __future__ import annotations

import json as _json
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import KindVerbs, label, register_kind_verbs, verbose_of
from coffer.surfaces.cli._resolve import resolve_ref

app = typer.Typer(help="Manage skills (AgentSkills standard)")
_console = Console()


def _agent_names(c: httpx.Client, *, verbose: bool) -> dict[str, str]:
    """``agent uid -> agent name``, read once per command.

    A stored scope holds agent UIDS, and printing those would hand the reader a
    column of hex they cannot match to anything they typed. The listing is
    fetched once and every scope on the page is rendered against it.
    """
    r = c.get("/resources", params={"kind": "agent"})
    _cli_client.check(r, verbose=verbose)
    return {a["uid"]: a["name"] for a in r.json()["resources"]}


def _scope_label(skill: dict[str, Any], agent_names: dict[str, str]) -> str:
    """Render the delivery rule: a skill reaches an agent iff it is enabled and
    that agent is inside its scope. ``coffer skill scope <name>`` edits the
    scope; ``coffer skill enable|disable <name>`` flips the flag."""
    if not skill["enabled"]:
        return "disabled"
    scope: dict[str, list[str] | None] | None = skill["scope"]
    if scope is None:
        return "everywhere"
    agents = scope.get("agents")
    if agents is None:
        return "everywhere"
    # A uid no agent answers to is shown verbatim rather than dropped: it is a
    # real entry of the stored scope, and hiding it would make the printed reach
    # narrower than the one the daemon applies.
    named = [agent_names.get(uid, uid) for uid in agents]
    return "agents: " + (", ".join(named) if named else "none")


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List managed skills."""
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/skills")
        _cli_client.check(r, verbose=verbose)
        # Only the rendered table spells a scope out; `--json` hands the stored
        # uids over untouched, so the lookup is skipped rather than paid for a
        # caller that is not going to read it.
        agent_names = {} if output_json else _agent_names(c, verbose=verbose)
    items = r.json()["items"]
    if output_json:
        typer.echo(_json.dumps(items, indent=2))
        return
    table = Table(title="Skills")
    for col in ("Name", "Source", "Scope", "Delivered to", "Hash"):
        table.add_column(col)
    for it in items:
        delivered = ", ".join(b["agent_name"] for b in it["bindings"])
        table.add_row(
            label(it),
            it["source"]["type"],
            _scope_label(it, agent_names),
            delivered or "—",
            it["version_hash"][:12],
        )
    _console.print(table)


@app.command("show")
def show(
    ctx: typer.Context,
    ref: str = typer.Argument(..., metavar="NAME", help="Name or uid"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Show one skill, by name or uid."""
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_ref(c, "skill", ref, verbose=verbose)["uid"]
        r = c.get(f"/skills/{uid}")
        _cli_client.check(r, verbose=verbose)
        agent_names = {} if output_json else _agent_names(c, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"name:        {data['name']}")
    if data.get("title"):
        typer.echo(f"title:       {data['title']}")
    typer.echo(f"description: {data['description']}")
    typer.echo(f"source:      {data['source']['type']}")
    typer.echo(f"master:      {data['master_path']}")
    typer.echo(f"hash:        {data['version_hash']}")
    typer.echo(f"scope:       {_scope_label(data, agent_names)}")
    if data["bindings"]:
        typer.echo("delivered to:")
        for b in data["bindings"]:
            typer.echo(f"  - {b['agent_name']} ({b['link_mode'] or 'unknown'})")


@app.command("add")
def add(
    ctx: typer.Context,
    folder: str = typer.Argument(..., help="Local path to an existing skill folder"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Replace an existing skill of the same name"
    ),
    title: str | None = typer.Option(None, "--title", help="Display title (≤80 chars)"),
) -> None:
    """Import a skill from a local folder; its name comes from SKILL.md."""
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/skills/import", json={"path": folder, "overwrite": force})
        _cli_client.check(r, verbose=verbose)
        if title:
            t = c.patch(f"/resources/{r.json()['uid']}", json={"title": title})
            _cli_client.check(t, verbose=verbose)
    typer.echo(f"added: skill {r.json()['name']}")


register_kind_verbs(
    app,
    KindVerbs(
        kind="skill",
        noun="skill",
        verbs=frozenset({"edit", "rm", "enable", "disable", "scope"}),
        name_fixed=True,
        help={
            "rm": (
                "Remove a skill and tear down all its agent deliveries. "
                "A skill Coffer generates itself is refused (exit 5)."
            ),
            "enable": "Enable a skill: it is delivered to every agent in its scope.",
            "disable": "Disable a skill: its delivered links are withdrawn.",
        },
    ),
)


def _drift_table(title: str, entries: list[dict[str, Any]]) -> Table:
    table = Table(title=title)
    for col in ("Skill", "Agent", "Kind", "Target", "Remedy"):
        table.add_column(col)
    for e in entries:
        table.add_row(
            e["skill_name"],
            e["agent_name"] or "—",
            e["kind"],
            e["target_path"],
            e["suggested_remedy"],
        )
    return table


@app.command("verify")
def verify(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
    fix: bool = typer.Option(
        False,
        "--fix",
        help=(
            "Re-deliver repairable drift (missing/tampered links) from master;"
            " leaves foreign content untouched."
        ),
    ),
) -> None:
    """Report drift between bindings and on-disk symlinks."""
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    if fix:
        with c:
            r = c.post("/skills/repair")
            _cli_client.check(r, verbose=verbose)
        data = r.json()
        if output_json:
            typer.echo(_json.dumps(data, indent=2))
            if data["remaining"]["entries"]:
                raise typer.Exit(2)
            return
        remediated = data["remediated"]
        remaining = data["remaining"]["entries"]
        if remediated:
            _console.print(_drift_table("Repaired", remediated))
        else:
            typer.echo("nothing to repair")
        if remaining:
            _console.print(_drift_table("Still drifted — manual action needed", remaining))
            raise typer.Exit(2)
        return
    with c:
        r = c.post("/skills/verify")
        _cli_client.check(r, verbose=verbose)
    entries = r.json()["entries"]
    if output_json:
        typer.echo(_json.dumps(entries, indent=2))
        if entries:
            raise typer.Exit(2)
        return
    if not entries:
        typer.echo("no drift")
        return
    _console.print(_drift_table("Skill drift", entries))
    raise typer.Exit(2)

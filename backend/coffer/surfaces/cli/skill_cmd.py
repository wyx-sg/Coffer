"""coffer skill ... commands (local-folder import only).

Takes NAMES — the skill's, and the agent's where a command names one — and
resolves each to a uid through ``_resolve`` before it addresses a route
(ADR resource-identity-is-an-immutable-uid). An UNMANAGED skill is the one
exception: it is a folder on disk with no resource row, so there is no uid to
resolve and its directory name is what the route takes.
"""

from __future__ import annotations

import json as _json
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

app = typer.Typer(help="Manage skills (AgentSkills standard)")
_console = Console()


def _agent_names(c: httpx.Client) -> dict[str, str]:
    """``agent uid -> agent name``, read once per command.

    A stored scope holds agent UIDS, and printing those would hand the reader a
    column of hex they cannot match to anything they typed. The listing is
    fetched once and every scope on the page is rendered against it, the same
    way ``coffer scope show`` does it.
    """
    r = c.get("/resources", params={"kind": "agent"})
    r.raise_for_status()
    return {a["uid"]: a["name"] for a in r.json()["resources"]}


def _scope_label(skill: dict[str, Any], agent_names: dict[str, str]) -> str:
    """Render the delivery rule: a skill reaches an agent iff it is enabled and
    that agent is inside its scope. ``coffer scope set skill <name>`` edits the
    scope; ``coffer resource enable/disable skill <name>`` flips the flag."""
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
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List managed skills."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/skills")
        _cli_client.check(r, verbose=verbose)
        # Only the rendered table spells a scope out; `--json` hands the stored
        # uids over untouched, so the lookup is skipped rather than paid for a
        # caller that is not going to read it.
        agent_names = {} if output_json else _agent_names(c)
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
            it["name"],
            it["source"]["type"],
            _scope_label(it, agent_names),
            delivered or "—",
            it["version_hash"][:12],
        )
    _console.print(table)


@app.command("import")
def import_cmd(
    path: str = typer.Argument(..., help="Local path to an existing skill folder."),
    force: bool = typer.Option(
        False, "--force", "-f", help="Replace an existing skill of the same name"
    ),
) -> None:
    """Import a skill from a local folder."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/skills/import", json={"path": path, "overwrite": force})
        if r.status_code >= 400:
            typer.echo(r.json().get("error", {}).get("message", str(r.text)), err=True)
            raise typer.Exit(2)
    typer.echo(f"imported: skill {r.json()['name']}")


@app.command("show")
def show(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show one skill."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/skills/{resolve_uid(c, 'skill', name, verbose=verbose)}")
        _cli_client.check(r, verbose=verbose)
        agent_names = {} if output_json else _agent_names(c)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"name:        {data['name']}")
    typer.echo(f"description: {data['description']}")
    typer.echo(f"source:      {data['source']['type']}")
    typer.echo(f"master:      {data['master_path']}")
    typer.echo(f"hash:        {data['version_hash']}")
    typer.echo(f"scope:       {_scope_label(data, agent_names)}")
    if data["bindings"]:
        typer.echo("delivered to:")
        for b in data["bindings"]:
            typer.echo(f"  - {b['agent_name']} ({b['link_mode'] or 'unknown'})")


@app.command("rm")
def rm(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Remove a skill and tear down all its agent bindings.

    The refusal path matters as much as the success one: a skill Coffer
    generates answers DELETE with 409 RESOURCE_PROTECTED, and a bare
    ``raise_for_status()`` turned that into an httpx traceback. Routing
    through ``_client.check`` gives this door the same rendered message and
    exit code ``coffer resource delete skill <name>`` already gives.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    if not force and not typer.confirm(f"Really remove skill {name}?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/skills/{resolve_uid(c, 'skill', name, verbose=verbose)}")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed: skill {name}")


@app.command("unmanaged")
def unmanaged(
    ctx: typer.Context,
    agent: str = typer.Argument(..., help="Agent name."),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List skill-shaped folders in the agent's workspace that Coffer doesn't manage."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{resolve_uid(c, 'agent', agent, verbose=verbose)}/unmanaged-skills")
        _cli_client.check(r, verbose=verbose)
    items = r.json()["items"]
    if output_json:
        typer.echo(_json.dumps(items, indent=2))
        return
    table = Table(title=f"Unmanaged skills — {agent}")
    for col in ("Name", "Location", "Valid", "Reason"):
        table.add_column(col)
    for it in items:
        table.add_row(
            it["name"],
            it["location"],
            "✓" if it["valid"] else "✗",
            it["reason"] or "—",
        )
    _console.print(table)


@app.command("adopt")
def adopt(
    agent: str = typer.Argument(..., help="Agent name."),
    skill: str = typer.Argument(..., help="Unmanaged skill folder name."),
    location: str = typer.Option(
        "skills", "--location", help="Where the folder was discovered: skills | agents_dir."
    ),
) -> None:
    """Adopt an unmanaged skill folder into the Coffer master store."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            f"/agents/{resolve_uid(c, 'agent', agent)}/unmanaged-skills/{skill}/adopt",
            json={"location": location},
        )
        if r.status_code >= 400:
            typer.echo(r.json().get("error", {}).get("message", str(r.text)), err=True)
            raise typer.Exit(2)
    typer.echo(f"adopted: skill {r.json()['name']}")


@app.command("rm-unmanaged")
def rm_unmanaged(
    agent: str = typer.Argument(..., help="Agent name."),
    skill: str = typer.Argument(..., help="Unmanaged skill folder name."),
    location: str = typer.Option(
        "skills", "--location", help="Where the folder was discovered: skills | agents_dir."
    ),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Delete an unmanaged skill folder from the agent's workspace (from disk)."""
    if not force and not typer.confirm(
        f"Really delete unmanaged skill {skill!r} from agent {agent}?"
    ):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(
            f"/agents/{resolve_uid(c, 'agent', agent)}/unmanaged-skills/{skill}",
            params={"location": location},
        )
        if r.status_code >= 400:
            typer.echo(r.json().get("error", {}).get("message", str(r.text)), err=True)
            raise typer.Exit(2)
    typer.echo(f"deleted: unmanaged skill {skill} (agent {agent})")


@app.command("verify")
def verify(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json"),
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
    verbose = (ctx.obj or {}).get("verbose", False)
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
            table = Table(title="Repaired")
            for col in ("Skill", "Agent", "Kind", "Target", "Remedy"):
                table.add_column(col)
            for e in remediated:
                table.add_row(
                    e["skill_name"],
                    e["agent_name"] or "—",
                    e["kind"],
                    e["target_path"],
                    e["suggested_remedy"],
                )
            _console.print(table)
        else:
            typer.echo("nothing to repair")
        if remaining:
            table2 = Table(title="Still drifted — manual action needed")
            for col in ("Skill", "Agent", "Kind", "Target", "Remedy"):
                table2.add_column(col)
            for e in remaining:
                table2.add_row(
                    e["skill_name"],
                    e["agent_name"] or "—",
                    e["kind"],
                    e["target_path"],
                    e["suggested_remedy"],
                )
            _console.print(table2)
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
    table = Table(title="Skill drift")
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
    _console.print(table)
    raise typer.Exit(2)

"""coffer skill ... commands (local-folder import only)."""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Manage skills (AgentSkills standard)")
_console = Console()


@app.command("list")
def list_cmd(
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List managed skills."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/skills")
        r.raise_for_status()
    items = r.json()["items"]
    if output_json:
        typer.echo(_json.dumps(items, indent=2))
        return
    table = Table(title="Skills")
    for col in ("Name", "Source", "Bindings", "Hash"):
        table.add_column(col)
    for it in items:
        bindings = ", ".join(
            f"{b['agent_name']}{'+' if b['enabled'] else '-'}" for b in it["bindings"]
        )
        table.add_row(
            it["name"],
            it["source"]["type"],
            bindings or "—",
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
    typer.echo(f"imported: skill:{r.json()['name']}")


@app.command("show")
def show(
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show one skill."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/skills/{name}")
        if r.status_code == 404:
            typer.echo("not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"name:        {data['name']}")
    typer.echo(f"description: {data['description']}")
    typer.echo(f"source:      {data['source']['type']}")
    typer.echo(f"master:      {data['master_path']}")
    typer.echo(f"hash:        {data['version_hash']}")
    if data["bindings"]:
        typer.echo("bindings:")
        for b in data["bindings"]:
            typer.echo(f"  - {b['agent_name']}: {'enabled' if b['enabled'] else 'disabled'}")


@app.command("enable")
def enable(
    name: str = typer.Argument(...),
    agent: str = typer.Option(..., "--agent", "-a", help="Agent name."),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Enable a skill for one agent (creates a directory symlink)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            f"/skills/{name}/enable",
            json={"agent_name": agent, "force": force},
        )
        if r.status_code >= 400:
            typer.echo(r.json().get("error", {}).get("message", str(r.text)), err=True)
            raise typer.Exit(2)
    data = r.json()
    typer.echo(f"enabled: skill:{name} for agent:{agent} ({data['link_mode']})")


@app.command("disable")
def disable(
    name: str = typer.Argument(...),
    agent: str = typer.Option(..., "--agent", "-a"),
) -> None:
    """Disable a skill for one agent (removes the symlink)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/skills/{name}/disable", json={"agent_name": agent})
        if r.status_code >= 400:
            typer.echo(r.json().get("error", {}).get("message", str(r.text)), err=True)
            raise typer.Exit(2)
    typer.echo(f"disabled: skill:{name} for agent:{agent}")


@app.command("rm")
def rm(
    name: str = typer.Argument(...),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Remove a skill and tear down all its agent bindings."""
    if not force and not typer.confirm(f"Really remove skill:{name}?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/skills/{name}")
        if r.status_code == 404:
            typer.echo("not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    typer.echo(f"removed: skill:{name}")


@app.command("unmanaged")
def unmanaged(
    agent: str = typer.Argument(..., help="Agent name."),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List skill-shaped folders in the agent's workspace that Coffer doesn't manage."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{agent}/unmanaged-skills")
        if r.status_code == 404:
            typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
            raise typer.Exit(4)
        r.raise_for_status()
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
            f"/agents/{agent}/unmanaged-skills/{skill}/adopt",
            json={"location": location},
        )
        if r.status_code == 404:
            typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
            raise typer.Exit(4)
        if r.status_code >= 400:
            typer.echo(r.json().get("error", {}).get("message", str(r.text)), err=True)
            raise typer.Exit(2)
    typer.echo(f"adopted: skill:{r.json()['name']}")


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
        f"Really delete unmanaged skill {skill!r} from agent:{agent}?"
    ):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/agents/{agent}/unmanaged-skills/{skill}", params={"location": location})
        if r.status_code == 404:
            typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
            raise typer.Exit(4)
        if r.status_code >= 400:
            typer.echo(r.json().get("error", {}).get("message", str(r.text)), err=True)
            raise typer.Exit(2)
    typer.echo(f"deleted: unmanaged skill {skill} (agent:{agent})")


@app.command("verify")
def verify(
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
    c, _info = _cli_client.client_or_exit()
    if fix:
        with c:
            r = c.post("/skills/repair")
            r.raise_for_status()
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
        r.raise_for_status()
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

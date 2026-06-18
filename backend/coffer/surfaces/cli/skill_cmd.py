"""coffer skill ... commands."""

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
) -> None:
    """Import a skill from a local folder."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/skills/import", json={"path": path})
        if r.status_code >= 400:
            typer.echo(r.json().get("error", {}).get("message", str(r.text)), err=True)
            raise typer.Exit(2)
    typer.echo(f"imported: skill:{r.json()['name']}")


@app.command("fetch")
def fetch(
    git_url: str = typer.Argument(..., help="Public Git URL of the skill repo."),
    git_ref: str = typer.Option("main", "--ref", help="Branch / tag / commit."),
    git_subpath: str = typer.Option("", "--subpath", help="Path inside the repo."),
) -> None:
    """Fetch a skill from a public Git URL."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            "/skills/fetch",
            json={
                "git_url": git_url,
                "git_ref": git_ref,
                "git_subpath": git_subpath,
            },
            timeout=120,
        )
        if r.status_code >= 400:
            typer.echo(r.json().get("error", {}).get("message", str(r.text)), err=True)
            raise typer.Exit(2)
    typer.echo(f"fetched: skill:{r.json()['name']}")


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
    verdict = data.get("scan_verdict")
    if verdict:
        ack = " (risk acknowledged)" if data.get("risk_acknowledged") else ""
        if data.get("requires_acknowledgment"):
            ack = " (NEEDS ACKNOWLEDGMENT)"
        typer.echo(f"scan:        {verdict}, {data.get('scan_findings_count', 0)} finding(s){ack}")
    if data["bindings"]:
        typer.echo("bindings:")
        for b in data["bindings"]:
            typer.echo(f"  - {b['agent_name']}: {'enabled' if b['enabled'] else 'disabled'}")


@app.command("update")
def update(
    name: str = typer.Argument(...),
    allow_rename: bool = typer.Option(False, "--allow-rename"),
) -> None:
    """Refresh a Git-sourced skill from upstream."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/skills/{name}/update", json={"allow_rename": allow_rename}, timeout=120)
        if r.status_code >= 400:
            typer.echo(r.json().get("error", {}).get("message", str(r.text)), err=True)
            raise typer.Exit(2)
    data = r.json()
    if data["changed"]:
        rn = data.get("renamed_from")
        typer.echo(f"updated: {data['skill']['name']}" + (f" (renamed from {rn})" if rn else ""))
    else:
        typer.echo(f"already up to date: {name}")


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


@app.command("scan")
def scan(
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Re-scan a skill's content for risky patterns (trust layer)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/skills/{name}/scan")
        if r.status_code >= 400:
            typer.echo(r.json().get("error", {}).get("message", str(r.text)), err=True)
            raise typer.Exit(2)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        raise typer.Exit(2 if data["requires_acknowledgment"] else 0)
    verdict = data["verdict"] or "clean"
    typer.echo(f"verdict: {verdict} ({len(data['findings'])} finding(s))")
    if data["findings"]:
        table = Table(title=f"Scan findings — {name}")
        for col in ("Severity", "Rule", "File", "Line", "Message"):
            table.add_column(col)
        for f in data["findings"]:
            table.add_row(f["severity"], f["rule_id"], f["file"], str(f["line"]), f["message"])
        _console.print(table)
    if data["requires_acknowledgment"]:
        typer.echo(
            "risk not acknowledged — run `coffer skill acknowledge-risk "
            f"{name}` before enabling it for an agent",
            err=True,
        )
        raise typer.Exit(2)


@app.command("acknowledge-risk")
def acknowledge_risk(
    name: str = typer.Argument(...),
) -> None:
    """Acknowledge a skill's scan risk so it can be enabled for agents."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/skills/{name}/acknowledge-risk")
        if r.status_code >= 400:
            typer.echo(r.json().get("error", {}).get("message", str(r.text)), err=True)
            raise typer.Exit(2)
    typer.echo(f"risk acknowledged: skill:{name}")


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
) -> None:
    """Report drift between bindings and on-disk symlinks."""
    c, _info = _cli_client.client_or_exit()
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

"""``coffer scan``, ``coffer adopt`` and ``coffer discard`` — what agents hold
that Coffer does not manage yet.

One table with a ``kind`` column (spec resource-framework "Scan, adopt and
discard what Coffer does not manage"):

- ``agent`` — an installed agent that is not registered (``GET
  /agents/candidates``); its ref is the agent type;
- ``skill`` — a skill-shaped folder in a registered agent's skill locations that
  is not a Coffer-managed link (``GET /agents/{uid}/unmanaged-skills``); its ref
  is the folder's path;
- ``mcp`` — an MCP entry in a registered agent's own config files, Coffer's own
  entry excepted (``GET /agents/{uid}/mcp-entries``); its ref is
  ``<agent>:<entry>``.

``scan --ref`` shows one row in full. ``adopt`` and ``discard`` act on one row
by the ref the scan printed, re-scanned first so a ref that names nothing now
is refused before any change. A detected agent cannot be discarded: nothing of
Coffer's put it there.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import _scan_detail
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli._resolve import resolve_uid

adopt_app = typer.Typer(help="Bring one scanned item under Coffer's management")
discard_app = typer.Typer(help="Remove one scanned item from the agent that holds it")
_console = Console()

#: A per-agent read that does not apply to this agent's type answers one of
#: these; the scan skips that source rather than failing the whole table.
_NOT_APPLICABLE = (400, 404, 422)


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _agents(c: httpx.Client, only: str | None, *, verbose: bool) -> list[dict[str, Any]]:
    r = c.get("/resources", params={"kind": "agent"})
    _cli_client.check(r, verbose=verbose)
    agents = [dict(a) for a in r.json()["resources"]]
    if only is None:
        return agents
    uid = resolve_uid(c, "agent", only, verbose=verbose)
    return [a for a in agents if a["uid"] == uid]


def _agent_rows(c: httpx.Client, *, verbose: bool) -> list[dict[str, Any]]:
    r = c.get("/agents/candidates")
    _cli_client.check(r, verbose=verbose)
    return [
        {
            "kind": "agent",
            "agent": cand["suggested_name"],
            "ref": cand["type"],
            "detail": f"{cand['display_name']} at {cand['config_dir']}",
            "config_dir": cand["config_dir"],
            "suggested_name": cand["suggested_name"],
        }
        for cand in r.json()["candidates"]
    ]


def _skill_rows(c: httpx.Client, agent: dict[str, Any], *, verbose: bool) -> list[dict[str, Any]]:
    r = c.get(f"/agents/{agent['uid']}/unmanaged-skills")
    if r.status_code in _NOT_APPLICABLE:
        return []
    _cli_client.check(r, verbose=verbose)
    rows = []
    for it in r.json()["items"]:
        detail = f"{it['name']} ({it['location']})"
        if not it["valid"]:
            detail += f" — not adoptable: {it['reason'] or 'invalid'}"
        rows.append(
            {
                "kind": "skill",
                "agent": agent["name"],
                "ref": it["path"],
                "detail": detail,
                "name": it["name"],
                "location": it["location"],
                "valid": it["valid"],
                "agent_uid": agent["uid"],
            }
        )
    return rows


def _mcp_rows(c: httpx.Client, agent: dict[str, Any], *, verbose: bool) -> list[dict[str, Any]]:
    r = c.get(f"/agents/{agent['uid']}/mcp-entries")
    if r.status_code in _NOT_APPLICABLE:
        return []
    _cli_client.check(r, verbose=verbose)
    return [
        {
            "kind": "mcp",
            "agent": agent["name"],
            "ref": f"{agent['name']}:{it['name']}",
            "detail": f"{it['transport']} in {it['source']}",
            "name": it["name"],
            "source": it["source"],
            "matches_resource": it["matches_resource"],
            "agent_uid": agent["uid"],
        }
        for it in r.json()["items"]
        if not it["is_coffer"]
    ]


def scan_rows(
    c: httpx.Client,
    *,
    agent: str | None = None,
    kinds: tuple[str, ...] = ("agent", "skill", "mcp"),
    verbose: bool = False,
) -> list[dict[str, Any]]:
    """Every row a scan prints. Candidates belong to no registered agent, so a
    scan narrowed to one agent carries none."""
    rows: list[dict[str, Any]] = []
    if agent is None and "agent" in kinds:
        rows += _agent_rows(c, verbose=verbose)
    if "skill" in kinds or "mcp" in kinds:
        for a in _agents(c, agent, verbose=verbose):
            if "skill" in kinds:
                rows += _skill_rows(c, a, verbose=verbose)
            if "mcp" in kinds:
                rows += _mcp_rows(c, a, verbose=verbose)
    return rows


def scan(
    ctx: typer.Context,
    agent: str | None = typer.Option(None, "--agent", help="Only what this agent holds"),
    ref: str | None = typer.Option(
        None, "--ref", help="Show one row in full: a type, a folder path or <agent>:<entry>"
    ),
    source: str | None = typer.Option(
        None, "--source", help="With --ref on an mcp row: the config-file key"
    ),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List what agents hold that Coffer does not manage: agents, skills, MCP entries.

    With --ref, show that one row in full: an MCP entry's whole configuration
    (secret values withheld) or an unmanaged skill's metadata.
    """
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        if ref is not None:
            row = _row(c, _kind_of(ref), ref, verbose=verbose)
            _scan_detail.echo(
                row["kind"],
                _scan_detail.detail(c, row, source=source, verbose=verbose),
                output_json=output_json,
            )
            return
        rows = scan_rows(c, agent=agent, verbose=verbose)
    if output_json:
        typer.echo(_json.dumps({"rows": rows}, indent=2))
        return
    if not rows:
        typer.echo("nothing unmanaged found")
        return
    table = Table(title="Not managed by Coffer")
    for col in ("Kind", "Agent", "Ref", "Detail"):
        table.add_column(col)
    for row in rows:
        table.add_row(row["kind"], row["agent"], row["ref"], row["detail"])
    _console.print(table)


def _kind_of(ref: str) -> str:
    """Which kind of row a ref names, by the shape the scan gives each kind."""
    if ref.startswith(("/", "~", ".")):
        return "skill"
    return "mcp" if ":" in ref else "agent"


# --- one row by its ref ------------------------------------------------------------


def _row(c: httpx.Client, kind: str, ref: str, *, verbose: bool) -> dict[str, Any]:
    """The fresh scan row ``ref`` names, or a refusal that changed nothing."""
    if kind == "mcp":
        agent_name, sep, entry = ref.partition(":")
        if not sep or not agent_name or not entry:
            typer.echo(f"an mcp ref is <agent>:<entry>, got {ref!r}", err=True)
            raise typer.Exit(2)
        rows = scan_rows(c, agent=agent_name, kinds=("mcp",), verbose=verbose)
    else:
        rows = scan_rows(c, kinds=(kind,), verbose=verbose)
    wanted = _abs(ref) if kind == "skill" else ref
    for row in rows:
        if row["kind"] == kind and (_abs(row["ref"]) if kind == "skill" else row["ref"]) == wanted:
            return row
    typer.echo(f"{ref!r} names no {kind} row in a fresh scan — run: coffer scan", err=True)
    raise typer.Exit(int(ExitCode.NOT_FOUND))


def _abs(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def _confirm(question: str, yes: bool) -> None:
    if not yes and not typer.confirm(question):
        raise typer.Exit(1)


_YES = typer.Option(False, "--yes", "-y", "--force", "-f", help="Do not ask")
_SOURCE = typer.Option(None, "--source", help="Config-file key when the entry is in several files")


@adopt_app.command("agent")
def adopt_agent(
    ctx: typer.Context,
    ref: str = typer.Argument(..., metavar="TYPE", help="The agent type the scan printed"),
    name: str | None = typer.Option(None, "--name", help="Register under this name instead"),
) -> None:
    """Register a detected agent under its suggested name and config directory."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        row = _row(c, "agent", ref, verbose=verbose)
        body = {"type": ref, "name": name or row["suggested_name"], "config_dir": row["config_dir"]}
        r = c.post("/agents", json=body)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"adopted: agent {r.json().get('name', body['name'])}")


@adopt_app.command("skill")
def adopt_skill(
    ctx: typer.Context,
    ref: str = typer.Argument(..., metavar="PATH", help="The folder path the scan printed"),
) -> None:
    """Move an unmanaged skill folder into Coffer's master store and link it back."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        row = _row(c, "skill", ref, verbose=verbose)
        r = c.post(
            f"/agents/{row['agent_uid']}/unmanaged-skills/{row['name']}/adopt",
            json={"location": row["location"]},
        )
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"adopted: skill {r.json()['name']}")


@adopt_app.command("mcp")
def adopt_mcp(
    ctx: typer.Context,
    ref: str = typer.Argument(..., metavar="AGENT:ENTRY", help="The ref the scan printed"),
    name: str | None = typer.Option(None, "--name", help="Register the server under this name"),
    source: str | None = _SOURCE,
    secret: list[str] = typer.Option(  # noqa: B008 — typer option declaration
        [], "--secret", help="KEY=CREDENTIAL_REF for a secret-like env/header key (repeatable)"
    ),
) -> None:
    """Register an agent's direct MCP entry as a Coffer MCP server and remove it from the agent."""
    verbose = _verbose(ctx)
    secrets: dict[str, str] = {}
    for item in secret:
        key, sep, cred = item.partition("=")
        if not sep or not key or not cred:
            typer.echo(f"--secret must be KEY=CREDENTIAL_REF, got {item!r}", err=True)
            raise typer.Exit(2)
        secrets[key] = cred
    body: dict[str, Any] = {
        k: v for k, v in (("source", source), ("new_name", name)) if v is not None
    }
    if secrets:
        body["secrets"] = secrets
    c, _info = _cli_client.client_or_exit()
    with c:
        row = _row(c, "mcp", ref, verbose=verbose)
        r = c.post(f"/agents/{row['agent_uid']}/mcp-entries/{row['name']}/adopt", json=body)
        _adopt_refusal(r)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    typer.echo(f"adopted: {data['kind']} {data['name']}")


def _adopt_refusal(r: httpx.Response) -> None:
    """The two refusals an adoption answers with a hint of what to pass next."""
    if r.status_code < 400:
        return
    envelope = r.json().get("error", {})
    if r.status_code == 422 and envelope.get("code") == "ADOPT_SECRET_UNRESOLVED":
        typer.echo(envelope.get("message", "secret keys unresolved"), err=True)
        typer.echo("hint: pass --secret KEY=CREDENTIAL_REF for each key listed above", err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT))
    if r.status_code == 409:
        typer.echo(envelope.get("message", "name conflict"), err=True)
        suggested = (envelope.get("details") or {}).get("suggested_name")
        if suggested:
            typer.echo(f"hint: retry with --name {suggested}", err=True)
        raise typer.Exit(int(ExitCode.CONFLICT))


@discard_app.command("agent")
def discard_agent(ref: str = typer.Argument(..., metavar="TYPE")) -> None:
    """Refused: a detected agent was not put there by Coffer, so Coffer does not remove it."""
    typer.echo(
        f"a detected agent cannot be discarded: nothing of Coffer's put {ref!r} there "
        "— uninstall it with its own tools",
        err=True,
    )
    raise typer.Exit(1)


@discard_app.command("skill")
def discard_skill(
    ctx: typer.Context,
    ref: str = typer.Argument(..., metavar="PATH", help="The folder path the scan printed"),
    yes: bool = _YES,
) -> None:
    """Delete an unmanaged skill folder from the agent's skill location (from disk)."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        row = _row(c, "skill", ref, verbose=verbose)
        _confirm(
            f"Really delete unmanaged skill folder {row['ref']} from agent {row['agent']}?", yes
        )
        r = c.delete(
            f"/agents/{row['agent_uid']}/unmanaged-skills/{row['name']}",
            params={"location": row["location"]},
        )
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"deleted: unmanaged skill {row['name']} (agent {row['agent']})")


@discard_app.command("mcp")
def discard_mcp(
    ctx: typer.Context,
    ref: str = typer.Argument(..., metavar="AGENT:ENTRY", help="The ref the scan printed"),
    source: str | None = _SOURCE,
    yes: bool = _YES,
) -> None:
    """Remove an MCP entry from the agent's own config file (a .bak is kept)."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        row = _row(c, "mcp", ref, verbose=verbose)
        _confirm(f"Really remove MCP entry {row['name']!r} from agent {row['agent']}?", yes)
        params = {"source": source} if source is not None else None
        r = c.delete(f"/agents/{row['agent_uid']}/mcp-entries/{row['name']}", params=params)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed: mcp entry {row['name']} from agent {row['agent']}")

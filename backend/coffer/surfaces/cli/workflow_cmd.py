"""``coffer workflow …`` — delivery runs from the terminal (spec workflow FR-046).

Thin HTTP shells over the daemon, matching the other CLI groups and their
exit-code mapping (``_cli_client.check``).

One thing this group does on the caller's behalf rather than making them do it:
every mutating command carries the run's ``version`` (FR-015), and the CLI reads
the run immediately before sending so the terminal never has to hold a number
between two commands. That is a convenience, not a weakening — a concurrent
change between the read and the write still comes back as a conflict, which is
exactly what the optimistic lock is for. A caller who has a version in hand can
pass ``--version`` and skip the read.

There is no ``run say``: a run has no conversation of its own (FR-030). Every
conversation belongs to one task, so redirecting a run means saying it in the
task's own conversation — ``run show`` prints the task and its conversation is
where the developer speaks.

The template half lives in ``workflow_template_cmd`` because a template is a
Resource and speaks to a different route family, and a run's inputs live in
``workflow_inputs_cmd`` because they are the one thing here that does not move
the run; ``workflow`` wires all of them together so the person sees one command.
"""

from __future__ import annotations

import json as _json
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import (
    workflow_approval_cmd,
    workflow_inputs_cmd,
    workflow_template_cmd,
)

app = typer.Typer(help="Run and steer Coffer's delivery workflows")
run_app = typer.Typer(help="Workflow runs")
node_app = typer.Typer(help="One node of a run")
app.add_typer(run_app, name="run")
run_app.add_typer(workflow_inputs_cmd.app, name="inputs")
app.add_typer(node_app, name="node")
app.add_typer(workflow_template_cmd.app, name="template")
workflow_approval_cmd.register(app)

_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def _current_version(c: httpx.Client, run_id: str, *, verbose: bool) -> int:
    """The run's version right now, so the caller need not carry one."""
    r = c.get(f"/workflow/runs/{run_id}")
    _cli_client.check(r, verbose=verbose)
    payload: dict[str, Any] = r.json()
    run = payload.get("run", payload)
    return int(run["version"])


def _echo(data: object, output_json: bool, render: Any) -> None:
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
    else:
        render(data)


def _render_runs(payload: Any) -> None:
    items = payload.get("items", [])
    if not items:
        typer.echo("no runs yet — `coffer workflow run create` starts one")
        return
    table = Table(show_header=True, header_style="bold")
    for column in ("run", "title", "status", "at", "owner"):
        table.add_column(column)
    for item in items:
        position = " → ".join(
            part for part in (item.get("current_stage_key"), item.get("current_node_key")) if part
        )
        table.add_row(
            item["id"][:8],
            item["title"],
            item["status"],
            position or "—",
            "this machine" if item.get("owned_here") else item.get("machine_id", "")[:8],
        )
    _console.print(table)


def _render_run_detail(payload: Any) -> None:
    run = payload["run"]
    typer.echo(f"{run['title']}  [{run['status']}]  v{run['version']}")
    typer.echo(f"  template  {run.get('template_ref') or '—'}")
    typer.echo(f"  workdir   {run['workdir']}")
    if not run.get("owned_here", True):
        typer.echo(f"  owned by  {run['machine_id']} — read-only here")
    table = Table(show_header=True, header_style="bold")
    # ``conversation`` is the column a person actually acts through: a task IS
    # its conversation (FR-030), and ``actions`` says what that conversation
    # will accept once they are in it (FR-052).
    for column in ("stage", "node", "type", "status", "try", "conversation", "actions"):
        table.add_column(column)
    for stage in payload.get("stages", []):
        for node in stage.get("nodes", []):
            table.add_row(
                stage["name"],
                node["name"] + ("  (ad-hoc)" if node.get("adhoc") else ""),
                node["type"],
                node["status"],
                str(node.get("attempt", 1)),
                node.get("conversation_id") or "—",
                ", ".join(node.get("allowed_actions", [])) or "—",
            )
    _console.print(table)


@run_app.command("create")
def create_run(
    ctx: typer.Context,
    template: str = typer.Option(..., "--template", "-t", help="Template resource name"),
    title: str = typer.Option(..., "--title", help="What this run is delivering"),
    agent: str | None = typer.Option(None, "--agent", help="Default agent for the run's nodes"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Create a run. It starts in `draft` — `run start` sets it going.

    A template and a title is the whole of it (FR-011). The working directory is
    Coffer's own, one per run, and anything the run should read is mounted
    afterwards with `coffer workflow run inputs add` — which can also unmount
    it, which a flag on this command could never do.
    """
    body: dict[str, Any] = {"template": template, "title": title}
    if agent:
        body["agent"] = agent
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/workflow/runs", json=body)
        _cli_client.check(r, verbose=_verbose(ctx))
        payload = r.json()
    _echo(payload, output_json, lambda p: typer.echo(f"created run {p['id']}"))


@run_app.command("list")
def list_runs(
    ctx: typer.Context,
    status: str | None = typer.Option(None, "--status"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Every run on this vault, newest first."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/workflow/runs", params={"status": status} if status else None)
        _cli_client.check(r, verbose=_verbose(ctx))
        payload = r.json()
    _echo(payload, output_json, _render_runs)


@run_app.command("show")
def show_run(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Where the run is: its stages, its nodes, and what each one allows."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/workflow/runs/{run_id}")
        _cli_client.check(r, verbose=_verbose(ctx))
        payload = r.json()
    _echo(payload, output_json, _render_run_detail)


def _signal(ctx: typer.Context, run_id: str, signal: str, version: int | None) -> None:
    c, _info = _cli_client.client_or_exit()
    verbose = _verbose(ctx)
    with c:
        resolved = version if version is not None else _current_version(c, run_id, verbose=verbose)
        r = c.post(f"/workflow/runs/{run_id}/signals", json={"version": resolved, "signal": signal})
        _cli_client.check(r, verbose=verbose)
        typer.echo(f"{signal}: run is now {r.json()['status']}")


@run_app.command("start")
def start_run(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    version: int | None = typer.Option(None, "--version"),
) -> None:
    """Set the run going. It advances on its own from here."""
    _signal(ctx, run_id, "start", version)


@run_app.command("pause")
def pause_run(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    version: int | None = typer.Option(None, "--version"),
) -> None:
    """Stop starting new nodes. A node already running finishes."""
    _signal(ctx, run_id, "pause", version)


@run_app.command("resume")
def resume_run(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    version: int | None = typer.Option(None, "--version"),
) -> None:
    """Carry on from the last persisted event."""
    _signal(ctx, run_id, "resume", version)


@run_app.command("abort")
def abort_run(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    version: int | None = typer.Option(None, "--version"),
) -> None:
    """End the run. Pending approvals are superseded and nothing else runs."""
    _signal(ctx, run_id, "abort", version)


@run_app.command("events")
def run_events(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    after: int | None = typer.Option(None, "--after", help="Only events after this sequence"),
) -> None:
    """The run's event log — the record everything else is a projection of."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(
            f"/workflow/runs/{run_id}/events", params={"after_sequence": after} if after else None
        )
        _cli_client.check(r, verbose=_verbose(ctx))
        for event in r.json().get("items", []):
            where = " ".join(p for p in (event.get("stage_key"), event.get("node_key")) if p)
            typer.echo(f"{event['sequence']:>4}  {event['event_type']:<26} {where}")


@run_app.command("artifacts")
def run_artifacts(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """What the run has produced, and which node produced it."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/workflow/runs/{run_id}/artifacts")
        _cli_client.check(r, verbose=_verbose(ctx))
        payload = r.json()
    _echo(payload, output_json, lambda p: typer.echo(p.get("catalogue", "")))


@run_app.command("promote")
def promote(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    collection: str = typer.Option(..., "--collection", "-c"),
) -> None:
    """Copy the run's artifacts into a knowledge collection, leaving the run alone."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/workflow/runs/{run_id}/promotion", json={"collection": collection})
        _cli_client.check(r, verbose=_verbose(ctx))
        body = r.json()
    typer.echo(f"copied {body['copied']} file(s) into knowledge:{body['collection']}")


@run_app.command("relabel")
def relabel_run(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    title: str = typer.Option(..., "--title", help="What this delivery is called"),
    description: str | None = typer.Option(None, "--description", "-d"),
) -> None:
    """Rewrite what a run is called and what it is for. Moves nothing else."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(
            f"/workflow/runs/{run_id}",
            json={"title": title, "description": description},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"relabelled run {run_id}")


@run_app.command("delete")
def delete_run(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
) -> None:
    """Delete the run, its events and its directory. Conversations are kept."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/workflow/runs/{run_id}")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"deleted run {run_id}")


@node_app.command("act")
def node_act(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    node_key: str = typer.Argument(..., help="Node key, or adhoc:<slug>"),
    action: str = typer.Argument(..., help="start|feedback|complete|retry|skip|restore"),
    feedback: str | None = typer.Option(None, "--feedback", "-f"),
    waive_artifacts: bool = typer.Option(
        False, "--waive-artifacts", help="Complete despite a required artifact never being written"
    ),
    version: int | None = typer.Option(None, "--version"),
) -> None:
    """Act on one node. `show` lists what the node currently allows."""
    body: dict[str, Any] = {"action": action}
    if feedback is not None:
        body["feedback"] = feedback
    if waive_artifacts:
        body["waive_artifacts"] = True
    c, _info = _cli_client.client_or_exit()
    verbose = _verbose(ctx)
    with c:
        body["version"] = (
            version if version is not None else _current_version(c, run_id, verbose=verbose)
        )
        r = c.post(f"/workflow/runs/{run_id}/nodes/{node_key}/actions", json=body)
        _cli_client.check(r, verbose=verbose)
        attempt = r.json()
    typer.echo(f"{node_key}: {attempt['status']} (attempt {attempt['attempt']})")


@node_app.command("add")
def add_task(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
    stage_key: str = typer.Option(..., "--stage", "-s"),
    name: str = typer.Option(..., "--name", "-n"),
    instructions: str = typer.Option(..., "--instructions", "-i"),
    agent: str | None = typer.Option(None, "--agent"),
    workdir: str | None = typer.Option(None, "--workdir", help="A second repository, if needed"),
    version: int | None = typer.Option(None, "--version"),
) -> None:
    """Add unplanned work to a stage, with instructions of your own.

    It opens with the same shared context as any node and its artifacts are
    attributed the same way (FR-028).
    """
    body: dict[str, Any] = {"stage_key": stage_key, "name": name, "instructions": instructions}
    if agent:
        body["agent"] = agent
    if workdir:
        body["workdir"] = workdir
    c, _info = _cli_client.client_or_exit()
    verbose = _verbose(ctx)
    with c:
        body["version"] = (
            version if version is not None else _current_version(c, run_id, verbose=verbose)
        )
        r = c.post(f"/workflow/runs/{run_id}/tasks", json=body)
        _cli_client.check(r, verbose=verbose)
        attempt = r.json()
    typer.echo(f"added {attempt['node_key']} to {attempt['stage_key']}")

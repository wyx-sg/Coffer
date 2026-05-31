"""coffer chat ... commands (spec 008-builtin-agent-chat)."""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Chat with Coffer's built-in agent or a managed agent")
_console = Console()

_DEFAULT_TARGET = "builtin_agent:coffer"


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


@app.command("new")
def new(
    ctx: typer.Context,
    agent: str = typer.Option(
        _DEFAULT_TARGET,
        "--agent",
        "-a",
        help="Target agent ref: builtin_agent:<name> or agent:<name>.",
    ),
) -> None:
    """Start a new conversation with an agent."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/conversations", json={"target_ref": agent})
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(r.json()["id"])


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List conversations."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/conversations")
        _cli_client.check(r, verbose=_verbose(ctx))
    items = r.json()["items"]
    if output_json:
        typer.echo(_json.dumps(items, indent=2))
        return
    table = Table(title="Conversations")
    for col in ("ID", "Title", "Target", "Status"):
        table.add_column(col)
    for it in items:
        table.add_row(it["id"], it["title"] or "", it["target_ref"], it["status"])
    _console.print(table)


@app.command("show")
def show(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show a conversation and its message history."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/conversations/{conversation_id}")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"# {data['conversation']['title']} ({data['conversation']['target_ref']})")
    for m in data["messages"]:
        typer.echo(f"\n[{m['role']}] {m['content']}")
        for tc in m["tool_calls"]:
            typer.echo(f"  · tool {tc['tool']} -> {tc.get('result_summary')}")


@app.command("history")
def history(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Print a conversation's message history (alias of `show`)."""
    show(ctx, conversation_id, output_json)


@app.command("send")
def send(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(...),
    text: str = typer.Argument(...),
) -> None:
    """Send a message and stream the agent's reply."""
    c, _info = _cli_client.client_or_exit()
    with (
        c,
        c.stream("POST", f"/conversations/{conversation_id}/messages", json={"text": text}) as r,
    ):
        if r.status_code >= 400:
            r.read()
            _cli_client.check(r, verbose=_verbose(ctx))
            return
        for line in r.iter_lines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            ev = _json.loads(line[len("data:") :].strip())
            kind = ev.get("type")
            if kind == "text_delta":
                typer.echo(ev["text"], nl=False)
            elif kind == "tool_call":
                typer.echo(f"\n· calling {ev['tool']}", err=True)
            elif kind == "confirmation":
                typer.echo(
                    f"\n· confirmation needed for {ev['tool']} — approve with "
                    f"`coffer chat confirm {conversation_id} {ev['id']} --approve`",
                    err=True,
                )
            elif kind == "error":
                typer.echo(f"\n[error] {ev['message']}", err=True)
            elif kind == "done":
                typer.echo("")


@app.command("confirm")
def confirm(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(...),
    request_id: str = typer.Argument(...),
    approve: bool = typer.Option(True, "--approve/--deny", help="Approve or deny the tool call."),
) -> None:
    """Approve or deny a pending tool confirmation."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            f"/conversations/{conversation_id}/confirm",
            json={"request_id": request_id, "approve": approve},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo("approved" if approve else "denied")


@app.command("stop")
def stop(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(...),
) -> None:
    """Stop the in-flight turn for a conversation."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/conversations/{conversation_id}/stop")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo("stopped")


@app.command("rename")
def rename(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(...),
    title: str = typer.Argument(...),
) -> None:
    """Rename a conversation."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/conversations/{conversation_id}", json={"title": title})
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"renamed: {conversation_id}")


@app.command("archive")
def archive(ctx: typer.Context, conversation_id: str = typer.Argument(...)) -> None:
    """Archive a conversation."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/conversations/{conversation_id}/archive")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"archived: {conversation_id}")


@app.command("restore")
def restore(ctx: typer.Context, conversation_id: str = typer.Argument(...)) -> None:
    """Restore an archived conversation."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/conversations/{conversation_id}/restore")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"restored: {conversation_id}")


@app.command("rm")
def rm(
    ctx: typer.Context,
    conversation_id: str = typer.Argument(...),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Delete a conversation."""
    if not force and not typer.confirm(f"Really delete conversation {conversation_id}?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/conversations/{conversation_id}")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"deleted: {conversation_id}")

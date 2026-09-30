"""``coffer memory …`` — the memory layer from the terminal (spec memory
"Cover memory management on REST and the CLI").

``show``, ``edit`` and ``rm`` are the lifecycle verbs every kind shares
(``_kind_verbs``); there is no ``add``, because partitions are provisioned
only by aggregation ("Provision partitions only from aggregation"), and no
``enable`` or ``disable``, because every partition is served to every agent
("Serve every partition to every agent"). ``list`` is the kind's own: it reads
``/memory/partitions``, which counts each partition's notes and names the
repository it is keyed on. ``sync`` updates memory — aggregation, then a
distil pass over every partition that gained entries ("Update memory in one
action"). The delivery hook
(four events) in an agent's own settings file is part of that agent's Coffer
connection (``coffer agent connect``), not a command of this group.
A partition's notes, index, retirement record and file tree are plain files,
so this group has no command that lists or prints one: ``coffer path memory
[<partition>]`` names the directory. Whether the hook is installed is a part of
``coffer_connection`` in ``coffer agent show``.

``context`` is the exception to everything above: it prints the session-start
context the installed hook delivers — the hook itself runs ``coffer memory
hook`` (``domain.memory.delivery.hook_invocation``), which asks the daemon for
the same text at session start — and like the hook it must be fast and must
never fail: no detect-or-spawn, a short timeout, and any failure at all
(daemon not running, a slow response, a malformed one) degrades to printing
nothing and exiting 0.

Every other command takes a partition's **name**, because that is what a
person knows; each resolves once through ``_resolve`` to the uid the
routes address resources by (ADR resource-identity-is-an-immutable-uid).
``context`` deliberately takes ``--agent-uid``, the same spelling the hook
entry Coffer wrote into that agent's own settings file carries: a uid is
precisely what stops a rename from silently turning a fire into an
unattributable one — so there is no ``--agent`` and no fallback.
"""

from __future__ import annotations

import json as _json

import httpx
import typer
from rich.console import Console
from rich.table import Table

from coffer.infrastructure.daemon.bootstrap import live_daemon
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import memory_hook_cmd
from coffer.surfaces.cli._kind_verbs import KindVerbs, label, register_kind_verbs

#: The registry kind the partition-addressing commands resolve a name against.
#: Spelled here rather than imported from ``application.memory.service`` so a
#: CLI module keeps depending on the daemon's HTTP surface and nothing deeper.
_KIND_MEMORY = "memory"

app = typer.Typer(help="Browse and manage Coffer's memory layer")
_console = Console()

#: Generous for a local loopback call, tiny next to the 10s detect-or-spawn
#: timeout `client_or_exit()` would otherwise impose on every session start.
_CONTEXT_TIMEOUT_S = 3.0


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


@app.command("list")
def list_partitions(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List every partition, with its note count and repository."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/memory/partitions")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title="Memory partitions")
    table.add_column("name")
    table.add_column("notes", justify="right")
    table.add_column("repository")
    for p in data["partitions"]:
        # A partition nothing can resolve to any more is called out rather
        # than hidden: only the developer can decide that repository is not
        # coming back, and an orphan that says nothing simply sits there
        # undeliverable and unmentioned ("Report unresolvable partitions").
        where = p["repository_path"] or p["repository_key"]
        table.add_row(
            label(p),
            str(p["note_count"]),
            f"{where} (unresolvable)" if p["unresolvable"] else where,
        )
    _console.print(table)


register_kind_verbs(
    app,
    KindVerbs(kind=_KIND_MEMORY, noun="partition", verbs=frozenset({"show", "edit", "rm"})),
)


@app.command("sync")
def sync(ctx: typer.Context, output_json: bool = typer.Option(False, "--json")) -> None:
    """Update memory: read every registered agent's native memory, then distil.

    Every partition left holding undistilled entries is distilled in the same
    call; one whose distil pass is already running is reported as skipped.
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/memory/sync")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2) if output_json else r.text)


@app.command("context")
def context(
    agent_uid: str = typer.Option(
        ..., "--agent-uid", help="The uid of the agent whose hook is firing"
    ),
    cwd: str = typer.Option(..., "--cwd", help="The session's working directory"),
    ceiling_tokens: int = typer.Option(0, "--ceiling-tokens", help="0 = the server's default"),
    hook_event: str = typer.Option(
        "",
        "--hook-event",
        help="Print the text as this hook event's JSON additionalContext instead of plain",
    ),
) -> None:
    """Print the composed session-start context to stdout.

    This is the text the installed hook (``coffer memory hook``) delivers at
    session start, printed for you to read. It prints nothing, and exits 0,
    when the daemon is not running.
    \f
    The installed hook runs ``coffer memory hook``
    (``domain.memory.delivery.hook_invocation``), not this command — see the
    module docstring for why every failure here is silent rather than raised.

    ``--agent-uid`` says who fired, and only that: the payload is the same for
    every agent, and the uid travels so the daemon can record the fire against
    it ("Audit every delivery fire") and size the payload for that agent's
    hook output limit.

    ``--hook-event`` wraps the text as that event's JSON
    ``hookSpecificOutput.additionalContext``, the shape Codex reads a hook's
    context from; without it the text is printed plain.

    Like ``coffer memory hook``, it takes a uid and not a name, and there is
    deliberately no ``--agent`` alias: a uid is the spelling a rename cannot
    change (ADR resource-identity-is-an-immutable-uid).
    """
    try:
        info = live_daemon()
        if info is None:
            return
        payload: dict[str, object] = {
            "agent_uid": agent_uid,
            "cwd": cwd,
            "record_fired": True,
        }
        if ceiling_tokens > 0:
            payload["ceiling_tokens"] = ceiling_tokens
        resp = httpx.post(
            f"http://127.0.0.1:{info.port}/api/v1/memory/context",
            json=payload,
            headers={"X-Coffer-Token": info.token, "X-Coffer-Actor": "cli"},
            timeout=_CONTEXT_TIMEOUT_S,
        )
        if resp.status_code != 200:
            return
        text = resp.json().get("text")
        if not text:
            return
        if hook_event:
            typer.echo(_json.dumps(_hook_output(hook_event, text), ensure_ascii=False))
        else:
            typer.echo(text)
    except Exception:
        return


def _hook_output(event: str, text: str) -> dict[str, object]:
    """The JSON a hook prints to add context: the shape Codex documents for
    ``SessionStart`` (and Claude Code accepts too)."""
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


# The three moments after session start: the hook every installed entry runs,
# the authored triggers, and the delivery views (``memory_hook_cmd``).
app.command("hook")(memory_hook_cmd.hook)
app.command("delivered")(memory_hook_cmd.delivered)
app.add_typer(memory_hook_cmd.trigger_app, name="trigger")

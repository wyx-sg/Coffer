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
``coffer_connection`` in ``coffer agent show``. The exact session-start text
each agent is given is ``coffer memory delivered <partition>``.

Every command takes a partition's **name**, because that is what a person
knows; each resolves once through ``_resolve`` to the uid the routes address
resources by (ADR identity-is-the-uid-inside-the-file).
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import memory_hook_cmd
from coffer.surfaces.cli._kind_verbs import KindVerbs, label, register_kind_verbs

#: The registry kind the partition-addressing commands resolve a name against.
#: Spelled here rather than imported from ``application.memory.service`` so a
#: CLI module keeps depending on the daemon's HTTP surface and nothing deeper.
_KIND_MEMORY = "memory"

app = typer.Typer(help="Browse and manage Coffer's memory layer")
_console = Console()


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


# The three moments after session start: the hook every installed entry runs,
# the authored triggers, and the delivery views (``memory_hook_cmd``).
app.command("hook")(memory_hook_cmd.hook)
app.command("delivered")(memory_hook_cmd.delivered)
app.add_typer(memory_hook_cmd.trigger_app, name="trigger")

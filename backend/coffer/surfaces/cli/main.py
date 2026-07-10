"""Coffer CLI composition root."""

from __future__ import annotations

import typer

from coffer.surfaces.cli import (
    agent_cmd,
    audit_cmd,
    backup_cmd,
    channel_cmd,
    credentials_cmd,
    daemon_cmd,
    knowledge_base_cmd,
    knowledge_base_source_cmd,  # noqa: F401 — registers `kb check-sources`/`update-source` onto kb app
    memory_cmd,
    memory_merge_cmd,  # noqa: F401 — registers `memory merge-scan`/`merge` onto memory app
    provider_cmd,
    resource_cmd,
    retention_cmd,
    scope_cmd,
    skill_cmd,
    sync_cmd,
    transcript_cmd,
)
from coffer.surfaces.cli import mcp as mcp_cmd

app = typer.Typer(help="Coffer CLI", no_args_is_help=True)


@app.callback()
def root(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show full tracebacks and HTTP request/response context on error.",
    ),
) -> None:
    """Coffer — local-first AI agent vault."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


app.add_typer(daemon_cmd.app, name="daemon")
app.add_typer(resource_cmd.app, name="resource")
app.add_typer(scope_cmd.app, name="scope")
app.add_typer(audit_cmd.app, name="audit")
app.add_typer(retention_cmd.app, name="retention")
app.add_typer(mcp_cmd.app, name="mcp")
app.add_typer(credentials_cmd.app, name="credentials")
app.add_typer(agent_cmd.app, name="agent")
app.add_typer(channel_cmd.app, name="channel")
app.add_typer(skill_cmd.app, name="skill")
app.add_typer(knowledge_base_cmd.app, name="kb")
app.add_typer(memory_cmd.app, name="memory")
app.add_typer(provider_cmd.app, name="provider")
app.add_typer(sync_cmd.app, name="sync")
app.add_typer(transcript_cmd.app, name="transcript")

# Vault-level backup / restore are top-level verbs (not under `daemon`): they
# operate on the on-disk vault offline, independent of the daemon lifecycle.
app.command("backup")(backup_cmd.backup)
app.command("restore")(backup_cmd.restore)

# Machines fleet view is a top-level verb too (Task 15): the frontend
# Machines nav item isn't really "sync configuration", so it gets its own
# top-level command — same implementation as `coffer sync machines`
# (imported, not duplicated) so the two stay identical by construction,
# --rename included.
app.command("machines")(sync_cmd.machines)


def run() -> None:
    """Entry point for the `coffer` script in pyproject.toml."""
    app()


if __name__ == "__main__":
    run()

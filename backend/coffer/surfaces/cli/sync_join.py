"""What ``coffer sync adopt`` says before it joins (spec vault-sync "Report a
join before applying it").

Split out of ``sync_cmd.py`` for the file-size tier. The command asks the
daemon what the join would be (``GET /sync/join``), prints the case, the day
this machine last converged and the counts, and only then asks to go ahead. A
join is explicit, so a terminal that cannot answer the question is refused
rather than taken as a yes; ``--yes`` is how a script says it read the terms.
"""

from __future__ import annotations

import sys
from typing import Any

import typer
from rich.console import Console

from coffer.surfaces.cli._options import ExitCode


def interactive() -> bool:
    """Whether a person can answer the prompt. A seam for the tests."""
    return sys.stdin.isatty()


def print_join_preview(console: Console, preview: dict[str, Any], *, lead: str = "Joining") -> None:
    """The join, stated: its case, the day, the counts. ``lead`` is "Joining"
    before an adopt and "Would join" on a round that only detected it."""
    case = preview.get("case")
    last = preview.get("last_converged_on")
    indent = lead[: len(lead) - len(lead.lstrip())]
    if case == "returning":
        console.print(
            f"{lead} this remote as a [bold]returning[/bold] machine: its id is in the "
            "registry, so it resumes from the base it last converged on"
            + (f" ({str(preview['base'])[:12]})." if preview.get("base") else ".")
        )
    elif case == "new":
        console.print(f"{lead} this remote as a [bold]new[/bold] machine: it takes the union.")
    else:
        console.print(
            f"{indent}[yellow]This machine synced with this remote before, but the commit "
            "it reached is gone from the remote's history.[/yellow]"
        )
    console.print(f"{indent}  last converged here: {last or 'never'}")
    changed = preview.get("remote_changed")
    if changed is not None:
        console.print(f"{indent}  documents the remote changed since: {changed}")
    console.print(f"{indent}  documents this vault holds: {preview.get('vault_documents') or 0}")


def confirm_join(console: Console, preview: dict[str, Any], *, yes: bool) -> None:
    """Refuse or ask, before anything is applied. Returns only to go ahead."""
    if preview.get("case") == "ambiguous":
        console.print(
            "  Nothing was applied. Choose: 'coffer sync adopt --keep-local' publishes "
            "this vault's documents as additions (which may bring back what others "
            "deleted), 'coffer sync rebuild' replaces this vault with the remote's."
        )
        raise typer.Exit(ExitCode.CONFLICT)
    if yes:
        return
    if not interactive():
        console.print("[red]refusing to join without confirmation[/red]: re-run with --yes")
        raise typer.Exit(ExitCode.INVALID_USAGE)
    typer.confirm("Join this remote?", abort=True)

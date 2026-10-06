"""The output half of the command line contract (``_io`` re-exports it).

Printing an answer (as JSON or for a person), a plain table, and the exit 9
a change that waits on approvals ends with (spec resource-framework "Offer
every management operation on the command line").
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

import typer

from coffer.surfaces.cli._options import ExitCode


def emit(value: Any, *, as_json: bool, human: Callable[[Any], None] | None = None) -> None:
    if as_json:
        typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))
        return
    if human is not None:
        human(value)
        return
    if value is None:
        typer.echo("done")
    elif isinstance(value, (dict, list)):
        typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    else:
        typer.echo(str(value))


def table(rows: list[Mapping[str, Any]], columns: list[str]) -> None:
    """A plain aligned table of ``columns`` (no colours: agents read it)."""
    if not rows:
        typer.echo("(none)")
        return
    cells = [[_cell(r.get(c)) for c in columns] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(columns)]
    typer.echo("  ".join(c.upper().ljust(widths[i]) for i, c in enumerate(columns)).rstrip())
    for row in cells:
        typer.echo("  ".join(v.ljust(widths[i]) for i, v in enumerate(row)).rstrip())


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    return text if len(text) <= 60 else text[:57] + "..."


def pending_approvals(value: Any) -> list[str]:
    """The approval ids an answer says a change waits on, wherever it puts them.

    A list (``pending_approvals``, ``approval_ids``), one id named as pending
    (``pending_approval_id``), or one ``approval_id`` beside a state that is
    ``pending`` (``{"local_access": "pending", "approval_id": …}``)."""
    if not isinstance(value, dict):
        return []
    ids: list[str] = []
    for key in ("pending_approvals", "approval_ids"):
        found = value.get(key)
        if isinstance(found, list):
            ids += [str(i) for i in found]
    single = value.get("pending_approval_id")
    if isinstance(single, str) and single:
        ids.append(single)
    named = value.get("approval_id")
    if isinstance(named, str) and named and "pending" in value.values():
        ids.append(named)
    return list(dict.fromkeys(ids))


def report_pending(value: Any, *, as_json: bool) -> None:
    """Exit 9 with the approve command when ``value`` waits on approvals."""
    ids = pending_approvals(value)
    if not ids:
        return
    command = "coffer approval approve " + " ".join(ids)
    if as_json:
        typer.echo(
            json.dumps(
                {"status": "pending_approval", "approval_ids": ids, "next": command},
                ensure_ascii=False,
            ),
            err=True,
        )
    else:
        typer.echo(f"waiting for approval: {', '.join(ids)}", err=True)
        typer.echo(f"next: {command}", err=True)
    raise typer.Exit(int(ExitCode.APPROVAL_PENDING))


__all__ = ["emit", "pending_approvals", "report_pending", "table"]

"""How ``coffer sync`` prints a round, shared by its command modules."""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console

_console = Console()

#: Round statuses that leave something for a person to do.
NEEDS_PERSON = frozenset(
    {
        "stopped",
        "held",
        "waiting_on_edit",
        "join_required",
        "auth_failed",
        "unreachable",
        "push_failed",
        "plaintext_found",
        "paused_cloud_folder",
        "remote_too_new",
        "remote_too_old",
        "failed",
    }
)

#: What to do next, by the round's status.
_NEXT = {
    "stopped": "see the files with 'coffer sync conflicts', answer each with 'coffer sync "
    "resolve', then 'coffer sync continue'",
    "held": "review with 'coffer sync hold', then 'coffer sync hold --confirm' or --restore",
    "waiting_on_edit": "an edit of yours on that file is not settled yet; the next round retries",
    "join_required": "run 'coffer sync join' to see what joining would do, and join",
    "auth_failed": "check the push token ('coffer sync remote set --secret-ref ...')",
    "paused_cloud_folder": "move the vault out of the synchronised folder",
    "plaintext_found": "move each value into a secret ('coffer sync status --prompt' hands it to "
    "your agent) and run 'coffer sync now', or 'coffer sync push-anyway' if it is not a secret",
}


def print_plaintext(found: list[dict[str, Any]]) -> None:
    """Where each plaintext secret is: file, line and key, never the value."""
    for f in found[:20]:
        where = "" if f.get("current", True) else "  (only in an unpushed commit)"
        _console.print(f"    [red]{f['path']}:{f['line']}[/red]  {f['key']}{where}")
    if len(found) > 20:
        _console.print(f"    and {len(found) - 20} more")


def verbose_of(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def changes(label: str, items: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.get("status", "?")] = counts.get(item.get("status", "?"), 0) + 1
    marks = {"added": "+", "modified": "~", "removed": "-"}
    parts = [f"{marks.get(k, k)}{v}" for k, v in sorted(counts.items())]
    return f"{label} {' '.join(parts) if parts else 'nothing'}"


def print_round(run: dict[str, Any], *, detail: bool = True) -> None:
    status = run.get("status", "?")
    style = "yellow" if status in NEEDS_PERSON else "green"
    _console.print(f"[{style}]{status}[/{style}]  round {run.get('id') or '—'}")
    if run.get("with_machines"):
        _console.print(f"  with {', '.join(run['with_machines'])}")
    _console.print(
        "  "
        + changes("pulled", run.get("applied") or [])
        + "  ·  "
        + changes("pushed", run.get("pushed") or [])
    )
    if run.get("from_commit") or run.get("to_commit"):
        a = (run.get("from_commit") or "")[:8] or "∅"
        b = (run.get("to_commit") or "")[:8] or "∅"
        _console.print(f"  commits {a}..{b}")
    if run.get("conflicts"):
        _console.print(f"  [yellow]{run['conflicts']} conflicting file(s)[/yellow]")
    if run.get("held"):
        _console.print(f"  [yellow]{run['held']} file(s) held[/yellow]")
    if run.get("path"):
        _console.print(f"  file: {run['path']}")
    if run.get("detail"):
        _console.print(f"  {run['detail']}")
    if run.get("plaintext"):
        print_plaintext(run["plaintext"])
    if run.get("folded"):
        _console.print(
            f"  folded {run['folded']} unpushed commit(s) into one: a value removed since "
            "was not pushed"
        )
    if detail:
        for c in (run.get("applied") or [])[:20]:
            _console.print(f"    {c['status']:<8} {c['path']}")
    step = _NEXT.get(status)
    if step:
        _console.print(f"  next: {step}")


__all__ = ["NEEDS_PERSON", "changes", "print_plaintext", "print_round", "verbose_of"]

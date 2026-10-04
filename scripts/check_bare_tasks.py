#!/usr/bin/env python3
"""Keep background tasks on the supervisor: no new bare ``create_task``.

Work that outlives the call that started it goes through
``coffer.application.runtime.supervisor`` (``spawn`` / ``spawn_restarting``),
which names the task, logs a crash with that name the moment it happens, counts
it for ``GET /api/v1/daemon/status``, and cancels whatever is left at shutdown.
A bare ``asyncio.create_task`` has none of that: a task that raises dies
silently until the garbage collector reports it, if ever.

This script parses every module under ``backend/coffer/`` and counts calls to
``create_task`` and ``ensure_future`` (on ``asyncio``, a loop, a task group —
any receiver). A file may make exactly as many as :data:`ALLOWED` lists for it,
each with the reason it is not background work: almost always a task the same
function awaits or cancels before it returns (the two sides of an
``asyncio.wait`` race, a shielded write), which is structured concurrency and
has an owner who sees its result. Two ways to fail:

* a file makes more such calls than it is allowed — a new bare task. Use
  ``spawn`` instead, or, if the task really is awaited in place, add it here
  with its reason;
* a file makes fewer than it is allowed — the entry is stale. Lower it, so the
  list keeps meaning what it says.

The supervisor itself is the one module that calls ``create_task`` by design.
Tests are not scanned. Stdlib-only.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / "backend" / "coffer"
SUPERVISOR = PACKAGE_DIR / "application" / "runtime" / "supervisor.py"
CALLS = frozenset({"create_task", "ensure_future"})

#: ``path under backend/coffer -> (how many bare calls, why they are not background work)``.
ALLOWED: dict[str, tuple[int, str]] = {
    "surfaces/http/mcp/protocol_routes.py": (
        2,
        "the SSE stream races queue.get() against the stop event and cancels the loser",
    ),
    "surfaces/http/mcp/capability_routes.py": (
        3,
        "three discovery reads gathered in place and awaited by the route",
    ),
    "surfaces/http/mcp/config_test_routes.py": (
        1,
        "cancel_on_disconnect awaits its work task and cancels it in finally",
    ),
    "surfaces/shim/main.py": (
        4,
        "the shim is its own short-lived process; its pumps are awaited by asyncio.wait "
        "and its envelope tasks are drained when the process ends",
    ),
    "infrastructure/model_proxy/relay.py": (
        4,
        "per-request disconnect watcher, send/gone race and pump, each cancelled in finally",
    ),
    "infrastructure/chat/claude_sdk_agent.py": (
        1,
        "the event pump is awaited and cancelled by the turn that started it",
    ),
    "infrastructure/chat/codex_agent.py": (
        1,
        "the event pump is awaited and cancelled by the turn that started it",
    ),
    "infrastructure/chat/codex_stream.py": (
        2,
        "the eof/next-event race is awaited and cancelled in place",
    ),
    "infrastructure/daemon/entry.py": (
        1,
        "uvicorn's serve() is the process itself; entry awaits it",
    ),
}


def _is_task_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in CALLS
    return isinstance(func, ast.Name) and func.id in CALLS


def count_calls(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sum(1 for node in ast.walk(tree) if _is_task_call(node))


def check(
    package_dir: Path = PACKAGE_DIR, allowed: dict[str, tuple[int, str]] | None = None
) -> tuple[list[str], int]:
    """Problems found under ``package_dir``, and how many allow-listed calls it makes."""
    allowed = ALLOWED if allowed is None else allowed
    supervisor = package_dir / SUPERVISOR.relative_to(PACKAGE_DIR)
    counts: dict[str, int] = {}
    for path in sorted(package_dir.rglob("*.py")):
        if path == supervisor:
            continue
        n = count_calls(path)
        if n:
            counts[path.relative_to(package_dir).as_posix()] = n
    problems: list[str] = []
    for rel, n in counts.items():
        limit = allowed.get(rel, (0, ""))[0]
        if n > limit:
            problems.append(
                f"  backend/coffer/{rel}: {n} bare create_task/ensure_future call(s), "
                f"{limit} allowed — start background work with "
                "coffer.application.runtime.supervisor.spawn()"
            )
    for rel, (limit, _why) in allowed.items():
        n = counts.get(rel, 0)
        if n < limit:
            problems.append(
                f"  scripts/check_bare_tasks.py: {rel} is allowed {limit} but makes {n} — "
                "lower its entry"
            )
    return problems, sum(counts.values())


def main() -> int:
    problems, total = check()
    if problems:
        print("check_bare_tasks: FAIL")
        print("\n".join(problems))
        return 1
    print(f"check_bare_tasks: OK ({total} allow-listed calls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

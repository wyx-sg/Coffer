"""Read a command-line tool's whole interface from its own help.

``discover`` walks the tree: the tool's ``--help``, then each subcommand it
lists, recursively, with a depth, a node and a time bound. It asks the
:class:`HelpRunnerPort` for one thing only — a help text for a subcommand path
— so the walk can run nothing else. A subcommand whose help is the parent's
own (a tool that ignores what it does not know) is not a node, and ``help`` is
not walked into.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from coffer.domain.skill.cli_help import DiscoveryStatus, HelpNode, Interface
from coffer.domain.skill.cli_help_parse import parse_help

HelpFlag = Literal["--help", "-h", "help"]
MAX_DEPTH = 3
MAX_NODES = 200
TOTAL_BUDGET_SECONDS = 30.0
#: Subcommands that are not commands of the tool's own to describe.
_NOT_WALKED = frozenset({"help"})


@dataclass(frozen=True)
class HelpOutput:
    text: str
    truncated: bool = False
    timed_out: bool = False
    #: Why nothing was read (could not start); ``None`` when the tool ran.
    error: str | None = None


class HelpRunnerPort(Protocol):
    """Run ``<path> <subcommands...> <flag>`` and return what it printed.
    Blocking; the implementation guarantees nothing else is ever run."""

    def run(self, path: str, subcommands: Sequence[str], flag: HelpFlag) -> HelpOutput: ...


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _read(runner: HelpRunnerPort, path: str, sub: tuple[str, ...]) -> HelpOutput:
    """``--help``, then ``-h``, then (for the tool itself) ``help``: the first
    that prints anything."""
    flags: tuple[HelpFlag, ...] = ("--help", "-h", "help") if not sub else ("--help", "-h")
    last = HelpOutput("")
    for flag in flags:
        last = runner.run(path, sub, flag)
        if last.text.strip():
            return last
        if last.error is not None:
            break
    return last


def discover(
    runner: HelpRunnerPort,
    path: str,
    *,
    max_depth: int = MAX_DEPTH,
    max_nodes: int = MAX_NODES,
    budget: float = TOTAL_BUDGET_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    clock: Callable[[], datetime] = _now,
) -> Interface:
    deadline = monotonic() + budget
    root = _read(runner, path, ())
    if not root.text.strip():
        why = root.error or ("timed out" if root.timed_out else "printed nothing")
        return Interface(
            DiscoveryStatus.NO_HELP,
            discovered_at=clock(),
            message=f"{path} --help {why}.",
        )
    nodes = [parse_help(root.text, (), truncated=root.truncated)]
    queue: list[HelpNode] = [nodes[0]]
    incomplete = False
    while queue:
        parent = queue.pop(0)
        if len(parent.path) >= max_depth:
            incomplete = incomplete or any(s.name not in _NOT_WALKED for s in parent.subcommands)
            continue
        for sub in parent.subcommands:
            if sub.name in _NOT_WALKED:
                continue
            if len(nodes) >= max_nodes or monotonic() > deadline:
                incomplete = True
                queue.clear()
                break
            out = _read(runner, path, (*parent.path, sub.name))
            node = _node(out, (*parent.path, sub.name), parent)
            if node is None:
                continue
            nodes.append(node)
            queue.append(node)
    return Interface(DiscoveryStatus.OK, tuple(nodes), clock(), incomplete)


def _node(out: HelpOutput, path: tuple[str, ...], parent: HelpNode) -> HelpNode | None:
    if not out.text.strip():
        why = out.error or ("timed out" if out.timed_out else "printed no help")
        return HelpNode(path=path, error=why)
    if out.text.strip() == parent.raw.strip():
        return None
    return parse_help(out.text, path, truncated=out.truncated)


__all__ = [
    "MAX_DEPTH",
    "MAX_NODES",
    "TOTAL_BUDGET_SECONDS",
    "HelpFlag",
    "HelpOutput",
    "HelpRunnerPort",
    "discover",
]

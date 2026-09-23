"""How one mounted input is written into a task's context.

Split out of ``context_composer`` because these three are the only things in
that module that answer to the INPUT rather than to the message: what a link
points at, whether a repository is the run's own checkout, and what
``RunRow.inputs`` means as value objects. The composer decides the shape of the
message; this decides what one line of it says.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from coffer.domain.workflow.links import classify_link
from coffer.domain.workflow.run import REPO_MOUNT_WORKTREE, RunInput, RunInputKind

__all__ = ["link_line", "parse_inputs", "repo_line"]


def link_line(item: RunInput, label: str) -> str:
    """A mounted link, with what it points at when that can be recognised.

    Naming the provider is what saves the node a guess: "go and read this URL"
    is not one operation, and reaching for the wrong tool is a failed call the
    developer sees as the run stalling. An unrecognised link says nothing more
    than that it is a link, so the node fetches it rather than believing it
    was told something (spec workflow "Name what a mounted external reference
    points at").
    """
    provider = classify_link(item.ref)
    if provider is None:
        return f"- link `{item.ref}`{label}"
    return f"- link `{item.ref}`{label} — a {provider} page; read it with that tool"


def repo_line(item: RunInput, label: str) -> str:
    """A mounted repository, said honestly (spec workflow "Give a
    mounted repository its own checkout").

    A worktree is the run's own checkout and may be committed to freely; a link
    is somebody else's directory and the message says so, because a node told
    it has an isolated checkout when it has not will commit into the
    developer's tree.
    """
    if item.path is None:
        return f"- repo `{item.ref}`{label} — not checked out"
    if item.mount == REPO_MOUNT_WORKTREE:
        return (
            f"- repo `{item.path}`{label} — your own git worktree of `{item.ref}`, on a branch "
            f"of this run's. Work in it; the developer's own checkout is untouched."
        )
    return (
        f"- repo `{item.path}`{label} — a LINK to `{item.ref}`, which is not a git repository. "
        f"It is not a copy: anything you write there, you write in the original."
    )


def parse_inputs(raw: Sequence[Mapping[str, Any]]) -> tuple[RunInput, ...]:
    """``RunRow.inputs`` as value objects, skipping what it cannot read.

    Tolerant on purpose: the column is JSON written by a surface, and one
    malformed entry must cost that entry rather than the node's whole context.
    """
    parsed: list[RunInput] = []
    for item in raw:
        ref = item.get("ref")
        raw_kind = item.get("kind")
        if not isinstance(ref, str) or not ref or not isinstance(raw_kind, str):
            continue
        try:
            kind = RunInputKind(raw_kind)
        except ValueError:
            continue
        label = item.get("label")
        size = item.get("size")
        path = item.get("path")
        mount = item.get("mount")
        parsed.append(
            RunInput(
                kind=kind,
                ref=ref,
                label=label if isinstance(label, str) else None,
                size=size if isinstance(size, int) and not isinstance(size, bool) else None,
                path=path if isinstance(path, str) else None,
                mount=mount if isinstance(mount, str) else None,
            )
        )
    return tuple(parsed)

"""How one mounted input is written into a node's context, and how the
catalogue is cut to fit.

Split out of ``context_composer`` because these four are the only things in
that module that answer to the INPUT rather than to the message: what a link
points at, whether a repository is the run's own checkout, how much of the
catalogue fits, and what ``RunRow.inputs`` means as value objects. The composer
decides the shape of the message; this decides what one line of it says.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from coffer.application.workflow.context_budget import (
    CATALOGUE_SHARE,
    estimate_tokens,
    share_of,
)
from coffer.domain.workflow.links import classify_link
from coffer.domain.workflow.run import REPO_MOUNT_WORKTREE, RunInput, RunInputKind

__all__ = ["fit_catalogue", "link_line", "parse_inputs", "repo_line"]


def link_line(item: RunInput, label: str) -> str:
    """A mounted link, with what it points at when that can be recognised.

    Naming the provider is what saves the node a guess: "go and read this URL"
    is not one operation, and reaching for the wrong tool is a failed call the
    developer sees as the run stalling. An unrecognised link says nothing more
    than that it is a link, so the node fetches it rather than believing it
    was told something (FR-065).
    """
    provider = classify_link(item.ref)
    if provider is None:
        return f"- link `{item.ref}`{label}"
    return f"- link `{item.ref}`{label} — a {provider} page; read it with that tool"


def repo_line(item: RunInput, label: str) -> str:
    """A mounted repository, said honestly (FR-057).

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


def fit_catalogue(body: str, catalogue_path: str) -> str:
    """The catalogue, cut to its share of the budget, saying if it was cut.

    Trimmed from the OLDEST rows, which sort first: the catalogue is ordered by
    node then attempt, so the tail is what the run made most recently. The
    whole of it is on disk either way — this is the one part of the message
    that can be replaced by a path without losing anything, because the file it
    points at was regenerated a line ago.
    """
    allowance = share_of(CATALOGUE_SHARE)
    if estimate_tokens(body) <= allowance:
        return body
    lines = body.splitlines()
    kept: list[str] = []
    spent = 0
    for line in reversed(lines):
        spent += estimate_tokens(line)
        if spent > allowance:
            break
        kept.append(line)
    kept.reverse()
    dropped = len(lines) - len(kept)
    header = (
        f"_{dropped} older catalogue line(s) are omitted here — this run has produced more "
        f"artifacts than fit in the context budget. The whole catalogue is at "
        f"`{catalogue_path}`._"
    )
    return "\n".join([header, "", *kept])


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

"""The hand-off that asks an agent to merge an upstream update into local edits.

Spec skill-manager "Record an update merged into local edits". An update that
meets local edits offers keep mine or take theirs; the merge is a chore for
the person's agent, which this prompt hands over with what it needs — the
master folder (the only place it may edit), the files edited since the pin,
the commit range and where upstream can be read. Upstream is named by its
repository (without any credential in the URL) and commits rather than by the
preview's stage, which is gone once the dialog closes; the agent clones it
read-only itself. The person then records the merge (``update_merge``).
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence
from typing import TYPE_CHECKING

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.skill.folder_diff import FileChange
from coffer.domain.skill.git_url import display_url
from coffer.domain.skill.source import GitImportSource

if TYPE_CHECKING:
    from coffer.application.skill.update_ops import CommitLine

#: More commits than this are summarised; the agent reads the rest in git.
_MAX_COMMITS = 20
_MAX_FILES = 40


def _files(changes: list[FileChange], limit: int = _MAX_FILES) -> str:
    names = [f"{c.path} ({c.status})" for c in changes[:limit]]
    more = len(changes) - limit
    return ", ".join(names) + (f", and {more} more" if more > 0 else "")


def merge_handoff(
    *,
    name: str,
    master: pathlib.Path,
    source: GitImportSource,
    to_commit: str,
    commits: Sequence[CommitLine],
    changes: list[FileChange],
    local_changes: list[FileChange],
) -> str:
    """The prompt that asks an agent to merge ``to_commit`` into the local edits."""
    frm = source.commit
    url = display_url(source.url)
    folder = source.subpath or "the repository's top folder"
    facts = [
        f"Skill: {name}",
        f"Master folder (edit files here, and only here): {master}",
        f"Source: {url}, ref {source.ref or 'the default branch'}, folder {folder}",
        f"Pinned commit: {frm}; upstream commit: {to_commit}",
    ]
    if commits:
        shown = "; ".join(f"{c.id[:7]} {c.subject}" for c in commits[:_MAX_COMMITS])
        more = len(commits) - _MAX_COMMITS
        facts.append(f"Upstream commits: {shown}" + (f"; and {more} more" if more > 0 else ""))
    if local_changes:
        facts.append(f"Files I edited since the pin: {_files(local_changes)}")
    if changes:
        facts.append(f"Files the update changes: {_files(changes)}")
    facts.append(
        f"Once you're done I record the merge in Coffer: the pin moves to {to_commit[:7]} and the "
        "master folder's files stay exactly as you left them."
    )
    return render_handoff(
        Handoff(
            task=(
                f"Skill {name} has local edits, and its source has an update. Merge the update "
                "into my edits in the skill's master folder."
            ),
            facts=tuple(facts),
            steps=(
                f"Clone {url} into a temporary folder outside ~/.coffer and read what changed "
                f"between {frm[:7]} and {to_commit[:7]} in {folder}; only read it — never push.",
                "Merge upstream's changes into the master folder: keep the intent of my edits "
                "and take upstream's fixes and additions; where the two really disagree, ask me.",
                "Edit files in the master folder only; touch no other folder.",
                f"Show me the diff of the master folder against upstream {to_commit[:7]}, then "
                "tell me it is ready for me to record as merged; do not record it yourself.",
            ),
        )
    )


__all__ = ["merge_handoff"]

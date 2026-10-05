"""The hand-off that asks an agent to bring a skill's upstream update in.

Spec skill-manager "Hand a Git-imported skill's update to an agent". Coffer
never applies an update; the chore goes to the person's agent with what it
needs — the master folder (the only place it may edit), the commit range with
the commits' subjects, the files edited since the pin and where upstream can
be read. Upstream is named by its repository (without any secret in the URL)
and commits; the agent clones it read-only itself. The person then records
the merge (``update_merge``, "Record an update merged into local edits").
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence
from typing import TYPE_CHECKING

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.skill.git_url import display_url
from coffer.domain.skill.source import GitImportSource

if TYPE_CHECKING:
    from coffer.application.skill.update_ops import CommitLine

#: More commits than this are summarised; the agent reads the rest in git.
_MAX_COMMITS = 20
_MAX_FILES = 40


def _files(paths: list[str], limit: int = _MAX_FILES) -> str:
    more = len(paths) - limit
    return ", ".join(paths[:limit]) + (f", and {more} more" if more > 0 else "")


def update_prompt(
    *,
    name: str,
    master: pathlib.Path,
    source: GitImportSource,
    to_commit: str,
    commits: Sequence[CommitLine],
    local_edits: list[str],
) -> str:
    """The prompt that asks an agent to bring ``to_commit`` into the master folder."""
    frm = source.commit
    url = display_url(source.url)
    folder = source.subpath or "the repository's top folder"
    facts = [
        f"Skill: {name}",
        f"Master folder (edit files here, and only here): {master}",
        f"Source (read-only): {url}, ref {source.ref or 'the default branch'}, folder {folder}",
        f"Pinned commit: {frm}; upstream commit: {to_commit}",
    ]
    if commits:
        shown = "; ".join(f"{c.id[:7]} {c.subject}" for c in commits[:_MAX_COMMITS])
        more = len(commits) - _MAX_COMMITS
        facts.append(f"Upstream commits: {shown}" + (f"; and {more} more" if more > 0 else ""))
    facts.append(
        f"Files I edited since the pin: {_files(local_edits)}"
        if local_edits
        else "I have not edited the skill since the pin."
    )
    return render_handoff(
        Handoff(
            task=(
                f"Skill {name}'s source has an update. Bring it into the skill's master folder, "
                "keeping my local edits."
            ),
            facts=tuple(facts),
            steps=(
                f"Clone {url} into a temporary folder outside ~/.coffer and read what changed "
                f"between {frm[:7]} and {to_commit[:7]} in {folder}; only read it — never push.",
                "Bring the new commit's content into the master folder: keep the intent of my "
                "edits and take upstream's fixes and additions; where the two really disagree, "
                "ask me.",
                "Edit files in the master folder only; touch no other folder.",
                f"Show me the diff of the master folder against upstream {to_commit[:7]}.",
                "I record it as merged in Coffer myself — do not call Coffer to record it.",
            ),
        )
    )


__all__ = ["update_prompt"]

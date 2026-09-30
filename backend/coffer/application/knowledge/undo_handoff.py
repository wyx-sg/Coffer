"""The prompt for undoing a curation pass by hand when Coffer refuses to (spec
knowledge "Keep every document's history and undo a pass as a whole").

Coffer's undo is all or nothing: when a document the pass wrote was edited
since, putting it back would lose that edit, so the undo is refused and nothing
is written. Reversing the pass *and* keeping the later edit is a merge of
prose — a judgement, not a deterministic step — so it is handed to the
person's agent (``domain/handoff.py``). The prompt names the pass, every
document it touched, which of them changed since and in which version, and
where to read each diff; the agent edits the files and Coffer's history
records what it writes as an edit on disk, like any other.
"""

from __future__ import annotations

import pathlib
import shlex
from collections.abc import Mapping, Sequence

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.knowledge.history import ADDED, MODIFIED, REMOVED, Change

#: What the pass did to a document, as the prompt says it.
_DID = {ADDED: "created by the pass", MODIFIED: "changed", REMOVED: "deleted by the pass"}


def undo_pass_handoff(
    *,
    root: pathlib.Path,
    repo: pathlib.Path,
    prefix: str,
    change: Change,
    documents: Sequence[str],
    changed_since: Mapping[str, str],
) -> str:
    """The hand-off for undoing ``change`` by hand. ``documents`` are the
    document paths the pass touched, relative to the knowledge folder
    ``root``; ``changed_since`` maps each one edited since to the newest
    version that edited it. The history is the vault repository ``repo``'s,
    in which the knowledge folder is ``prefix/`` (ADR
    every-vault-write-is-a-validated-commit-naming-its-writer)."""
    git = f"git -C {shlex.quote(str(repo))}"
    version = change.version
    status = {d.path: d.status for d in change.documents}
    touched = "; ".join(
        f"{path} ({_DID.get(status.get(path, MODIFIED), 'changed')})" for path in documents
    )
    since = "; ".join(f"{path} (last changed in {later})" for path, later in changed_since.items())
    return render_handoff(
        Handoff(
            task=(
                f"Please undo the knowledge curation pass {version} by hand: reverse "
                "what the pass changed, but keep the edits made to those documents since."
            ),
            facts=(
                f"The pass: {change.meta.summary}.",
                f"The knowledge folder is {root}; document paths are relative to it.",
                f"Documents the pass changed: {touched}.",
                f"Edited since the pass: {since}. That is why Coffer refused to undo it, "
                "and why those edits must stay.",
                f"Coffer keeps its history in the vault's git repository {repo}, where the "
                f"knowledge folder is `{prefix}/`. What the pass did: "
                f"`{git} show {version} -- {prefix}`. What came after, per document: "
                f"`{git} log -p {version}..HEAD -- {prefix}/<document>`.",
            ),
            steps=(
                "For each document, remove what the pass added and put back what it "
                "removed, working the later edits in rather than overwriting them; a "
                "document the pass created and nobody edited since can simply be deleted.",
                "Edit only the files. Do not commit, reset or check out anything in that "
                "repository: Coffer records your edits in its history itself.",
                "Show me each document's result before you save it.",
            ),
        )
    )


__all__ = ["undo_pass_handoff"]

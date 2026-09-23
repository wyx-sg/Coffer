"""What a run READ, written down so it survives the run (spec workflow
"Promote what a run is made of into a knowledge collection").

Promotion copies the run's own bytes — its artifacts, its uploads, its notes.
A link, a knowledge collection and a repository are not the run's bytes: the
link is somebody else's page, the collection is already in this vault, and the
repository is a checkout that goes when the run does. Copying them is either
impossible or duplication.

What IS worth keeping is that this delivery read them. Six months later the
question asked of a collection is "where did this come from", and a list of the
addresses, collections and repositories one delivery worked from answers it in
a way no copy of their contents would.

So they become one markdown file. It is generated here rather than in the
store, because what distinguishes a link from a repository is a fact about
``RunInput`` and not about the filesystem.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.workflow.links import classify_link
from coffer.domain.workflow.run import RunInput, RunInputKind

#: The kinds this file records. The other two — an uploaded file and a note —
#: are copied bodily, so naming them here as well would say the same thing
#: twice about a file sitting in the same directory.
_RECORDED = (RunInputKind.LINK, RunInputKind.KNOWLEDGE, RunInputKind.REPO)


def references_markdown(title: str, inputs: Sequence[RunInput]) -> str | None:
    """The run's external references as a markdown file, or ``None``.

    ``None`` when the run read nothing but its own files, because an empty
    ``references.md`` in a collection is a question every later reader has to
    open to answer.
    """
    recorded = [item for item in inputs if item.kind in _RECORDED]
    if not recorded:
        return None
    lines = [
        f"# References — {title}",
        "",
        "What this delivery read and did not produce. Copied here as addresses",
        "rather than as contents: a page belongs to whoever published it, a",
        "collection is already in this vault, and a checkout went with the run.",
        "",
    ]
    lines.extend(_line(item) for item in recorded)
    return "\n".join(lines) + "\n"


def _line(item: RunInput) -> str:
    label = f" — {item.label}" if item.label else ""
    if item.kind is RunInputKind.LINK:
        provider = classify_link(item.ref)
        where = f" ({provider})" if provider else ""
        return f"- [{item.ref}]({item.ref}){where}{label}"
    if item.kind is RunInputKind.KNOWLEDGE:
        return f"- knowledge collection `{item.ref}`{label}"
    return f"- repository `{item.ref}`{label}"

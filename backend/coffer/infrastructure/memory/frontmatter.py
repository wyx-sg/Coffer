"""YAML frontmatter and atomic writes for the memory layer's markdown files.

Every file this layer writes — a note, a raw entry, the retirement record — is
a ``---``-fenced YAML block followed by a body, and this module is the only
place that reads or writes that block (PyYAML lives in infrastructure, and
:mod:`coffer.infrastructure.memory.store` is already at the file-size cap
without it).

It is deliberately **not** ``infrastructure/knowledge/frontmatter.py``, which
does the same job for the knowledge layer, and the difference is one line of
behaviour that matters here and nowhere else: knowledge strips the body's
surrounding newlines and re-adds exactly one, which is right for a file a human
hand-edits and wrong for a raw entry. A raw entry is an agent's own words
carried verbatim (spec memory "Keep raw entries verbatim and hidden"), so
``split(render(fm, body))`` must give back that body **byte for byte**,
including whatever whitespace the agent left at the end — otherwise "re-run the
distillation without re-reading the agents" quietly stops meaning what it says.
The import-linter fence between kinds forbids borrowing knowledge's module
anyway; this is what the two would have had to diverge into even if it did not.
"""

from __future__ import annotations

import pathlib
from typing import Any

import yaml

FENCE = "---"


def render_frontmatter(frontmatter: dict[str, Any], body: str) -> str:
    """Fence, YAML, fence, then ``body`` exactly as given.

    Key order is the caller's, not alphabetical: these files are read by people
    in a preview pane, and ``title`` belongs above ``search_terms`` whatever the
    alphabet thinks.
    """
    block = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).rstrip("\n")
    return f"{FENCE}\n{block}\n{FENCE}\n{body}"


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """The inverse of :func:`render_frontmatter`, recovering the body exactly.

    An unfenced file is all body, and a fenced block whose YAML is malformed
    degrades to an empty mapping rather than raising. Nothing under this tree is
    authored by hand, but everything under it is derived and rebuildable (see
    "Keep the memory tree derived and local"): one damaged file then costs one
    thin entry until the next pass rewrites it, where raising would cost the
    whole partition's listing.

    The closing fence must sit at **column 0**, and that is not a nicety. A
    frontmatter value may be prose — ``RETIRED.md`` keeps the whole retirement
    record above the fence precisely so a reason can say anything — and PyYAML
    writes a multi-line string as an *indented* continuation. A reason
    containing a horizontal rule therefore puts ``    ---`` inside the block,
    and a scan that stripped each line before comparing would end the
    frontmatter there: the record would come back empty, the exclusion list
    would come back empty with it, and every note retired for that reason would
    be re-opened on the next pass (see "Record retirements so they stick"). YAML
    never unindents a continuation to column 0, so this comparison cannot be
    fooled the same way.
    """
    if not text.startswith(FENCE):
        return {}, text
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i].rstrip() == FENCE:
            raw = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            try:
                loaded = yaml.safe_load(raw) if raw.strip() else {}
            except yaml.YAMLError:
                loaded = {}
            return (loaded if isinstance(loaded, dict) else {}), body
    return {}, text


def text_list(values: Any) -> tuple[str, ...]:
    """A YAML scalar-or-sequence read back as a tuple of strings.

    ``search_terms: worktree`` and ``search_terms: [worktree]`` mean the same
    thing to the person who would write either; a reader that accepted only the
    second would drop the terms rather than say so, and "Write each index line
    to stand on its own" has the index line restating them.
    """
    if isinstance(values, str):
        return (values,)
    if isinstance(values, list):
        return tuple(str(v) for v in values)
    return ()


def atomic_write(path: pathlib.Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temp file in the same directory.

    A pass interrupted halfway then leaves the previous file intact rather than
    a truncated one the next pass would read as truth — which matters most for
    ``RETIRED.md``, where a half-read exclusion list silently reinstates notes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(text.encode("utf-8"))
    tmp.replace(path)


def read_text(path: pathlib.Path) -> str:
    """One of this layer's files, decoded without newline translation.

    Bytes, not :meth:`pathlib.Path.read_text`, because that one opens in
    universal-newline mode and silently rewrites ``\\r\\n`` to ``\\n``. An agent
    whose memory file has CRLF endings — one edited on Windows, or by a tool
    that writes them — would then round-trip through ``.raw/`` as a body that is
    not what was read, which is the one thing the verbatim rule of "Keep raw
    entries verbatim and hidden" is for. The pair with :func:`atomic_write`,
    which writes bytes for the same reason.
    """
    return path.read_bytes().decode("utf-8")


__all__ = [
    "FENCE",
    "atomic_write",
    "read_text",
    "render_frontmatter",
    "split_frontmatter",
    "text_list",
]

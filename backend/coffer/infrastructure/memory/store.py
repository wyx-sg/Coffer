"""Reads and writes one partition's fact files.

Every fact is one Markdown file: a YAML frontmatter block carrying everything
structured about it, then the source's own words underneath (FR-020, FR-021).
The whole tree this module writes is derived and can be deleted and rebuilt
from the agents' native memory at any time (FR-023) — which only holds if a
fact that goes through this module comes back exactly as it went in. That is
why the frontmatter split/render here does not trim or reflow the body the
way ``infrastructure/knowledge/frontmatter.py`` does: knowledge's files only
have to look right to a human editing them by hand, but a fact file has to
satisfy ``read_fact(write_fact(f)) == f`` on the nose, including whatever
whitespace the body happened to end with. Writes are atomic (temp file +
replace), mirroring the knowledge layer's own helper.

``clear_facts`` exists because a rebuild starts from nothing (spec memory
"Deleting the memory tree and re-syncing reproduces the facts"): aggregation
calls it before writing the pass's facts back out, rather than trying to diff
the old tree against the new one.
"""

from __future__ import annotations

import pathlib
import shutil
from typing import Any

import yaml

from coffer.domain.error_base import CofferError
from coffer.domain.memory.fact import STATUS_ACTIVE, Fact, Origin
from coffer.domain.memory.partition import GLOBAL_PARTITION
from coffer.infrastructure.memory import paths

_FENCE = "---"


class FactNotFound(CofferError):  # noqa: N818
    code = "MEMORY_FACT_NOT_FOUND"

    def __init__(self, partition: str, slug: str) -> None:
        super().__init__(f"no fact {slug!r} in partition {partition!r}")
        self.partition = partition
        self.slug = slug


def _render(frontmatter: dict[str, Any], body: str) -> str:
    """Fence + YAML + fence, then the body untouched.

    Deliberately not the knowledge module's ``render_frontmatter``: that one
    strips the body's surrounding newlines before re-adding exactly one
    trailing newline, which is fine for a file a human reads but loses
    whatever whitespace the original body had — and a fact's body must come
    back byte-for-byte (see module docstring).
    """
    block = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).rstrip("\n")
    return f"{_FENCE}\n{block}\n{_FENCE}\n{body}"


def _split(text: str) -> tuple[dict[str, Any], str]:
    """The inverse of ``_render``: exact body recovery, malformed YAML degrades
    to an empty frontmatter dict rather than raising (mirrors the knowledge
    module's own tolerance for a hand-edited file with a stray colon)."""
    if not text.startswith(_FENCE):
        return {}, text
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == _FENCE:
            raw = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            try:
                loaded = yaml.safe_load(raw) if raw.strip() else {}
            except yaml.YAMLError:
                loaded = {}
            return (loaded if isinstance(loaded, dict) else {}), body
    return {}, text


def _atomic_write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _fact_to_frontmatter(fact: Fact) -> dict[str, Any]:
    return {
        "title": fact.title,
        "description": fact.description,
        "type": fact.type,
        "status": fact.status,
        "superseded_by": fact.superseded_by,
        "conflicts_with": list(fact.conflicts_with),
        "origins": [
            {
                "agent": o.agent,
                "native_path": o.native_path,
                "anchor": o.anchor,
                "captured_at": o.captured_at,
                "source_written_at": o.source_written_at,
            }
            for o in fact.origins
        ],
    }


def _frontmatter_to_fact(partition: str, slug: str, fm: dict[str, Any], body: str) -> Fact:
    raw_origins = fm.get("origins") or []
    origins = tuple(
        Origin(
            agent=str(o.get("agent", "")),
            native_path=str(o.get("native_path", "")),
            anchor=str(o.get("anchor", "")),
            captured_at=str(o.get("captured_at", "")),
            source_written_at=str(o.get("source_written_at", "")),
        )
        for o in raw_origins
        if isinstance(o, dict)
    )
    raw_conflicts = fm.get("conflicts_with") or []
    return Fact(
        slug=slug,
        title=str(fm.get("title", "")),
        description=str(fm.get("description", "")),
        type=str(fm.get("type", "")),
        body=body,
        partition=partition,
        origins=origins,
        status=str(fm.get("status") or STATUS_ACTIVE),
        superseded_by=str(fm.get("superseded_by", "")),
        conflicts_with=tuple(str(c) for c in raw_conflicts),
    )


def write_fact(fact: Fact) -> str:
    """Write one fact file, atomically. Returns the memory-root-relative path."""
    path = paths.fact_path(fact.partition, fact.slug)
    text = _render(_fact_to_frontmatter(fact), fact.body)
    _atomic_write(path, text)
    return paths.relative_of(path)


def read_fact(partition: str, slug: str) -> Fact:
    """Read one fact back. Raises ``FactNotFound`` when the file is absent."""
    path = paths.fact_path(partition, slug)
    if not path.is_file():
        raise FactNotFound(partition, slug)
    text = path.read_text(encoding="utf-8")
    fm, body = _split(text)
    return _frontmatter_to_fact(partition, slug, fm, body)


def list_facts(partition: str) -> tuple[Fact, ...]:
    """Every fact in ``partition``, ordered by slug for a stable listing."""
    directory = paths.facts_dir(partition)
    if not directory.is_dir():
        return ()
    slugs = sorted(p.stem for p in directory.glob("*.md"))
    return tuple(read_fact(partition, slug) for slug in slugs)


def list_partitions() -> tuple[str, ...]:
    """Every partition directory present on disk, ``global`` included when it
    exists — this module creates none of them itself (FR-013: aggregation
    creates partitions, not this substrate)."""
    root = paths.memory_root()
    if not root.is_dir():
        return ()
    return tuple(
        sorted(d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith("."))
    )


def delete_partition(name: str) -> None:
    """Remove a partition entirely, README/summary/facts included."""
    directory = paths.partition_dir(name)
    if directory.is_dir():
        shutil.rmtree(directory)


def clear_facts(partition: str) -> None:
    """Remove every fact file so a rebuild starts from nothing.

    Leaves ``README.md`` and ``summary.md`` alone — a partition and its
    self-description outlive the facts inside it being recomputed.
    """
    directory = paths.facts_dir(partition)
    if not directory.is_dir():
        return
    for file in directory.glob("*.md"):
        file.unlink()


def write_readme(partition: str, project_root: str) -> None:
    """Say what this partition is, restating its project root (FR-011).

    ``global`` is not a project, so it gets a fixed description of what it
    holds instead of a root to name — ``project_root`` is accepted for every
    partition so callers never need to branch on which one they are writing.
    """
    if partition == GLOBAL_PARTITION:
        body = (
            "# global\n\n"
            "Facts about the person, not any one project: preferences and "
            "standing instructions an agent learned, delivered wherever the "
            "developer is working.\n"
        )
    else:
        body = f"# {partition}\n\nFacts learned while working in `{project_root}`.\n"
    _atomic_write(paths.readme_path(partition), body)

"""Acceptance scenarios for notes, the distil pass, the index and the read paths.

Every test drives the real store under the per-test ``HOME`` and the real distil pass.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from coffer.application.memory.context import compose_context
from coffer.application.memory.distil import distil_partition
from coffer.application.memory.index import index_line
from coffer.application.memory.service import KIND_MEMORY
from coffer.domain.memory.note import (
    NOTE_TYPES,
    TYPE_FEEDBACK,
    TYPE_PROJECT,
    TYPE_USER,
    Note,
    Origin,
)
from coffer.domain.memory.reader import RawEntry
from coffer.infrastructure.memory import paths, raw_store, store
from coffer.infrastructure.memory.paths import UnsafeMemoryPath
from coffer.infrastructure.memory.raw_store import StoredRawEntry, write_raw_entry
from tests.unit.memory.conftest import (
    FakeResources,
    memory_service,
)

_PARTITION = "coffer"


def _raw(
    title: str,
    body: str,
    *,
    anchor: str = "",
    agent: str = "codex",
    description: str = "",
    type: str = TYPE_PROJECT,
    partition: str = _PARTITION,
    search_terms: tuple[str, ...] = (),
) -> StoredRawEntry:
    stored = StoredRawEntry(
        partition=partition,
        agent=agent,
        native_path=f"/native/{agent}/{anchor or title}.md",
        captured_at="2026-01-01T00:00:00+00:00",
        entry=RawEntry(
            title=title,
            description=description or body,
            type=type,
            body=body,
            anchor=anchor or title,
            project_root="/home/dev/coffer",
            search_terms=search_terms,
        ),
    )
    write_raw_entry(stored)
    return stored


def _existing_note(slug: str, body: str, *, stamp: str = "2025-01-01T00:00:00+00:00") -> Note:
    # The raw entry the note was distilled from is still standing: a note with
    # none left is retired by the pass (see "Retire a note whose raw entries are
    # all gone"), which is not what these scenarios are about.
    write_raw_entry(
        StoredRawEntry(
            partition=_PARTITION,
            agent="claude-code",
            native_path=f"/old/{slug}.md",
            captured_at=stamp,
            entry=RawEntry(
                title=slug,
                description=body,
                type=TYPE_PROJECT,
                body=body,
                anchor=slug,
                project_root="/home/dev/coffer",
            ),
        )
    )
    note = Note(
        slug=slug,
        title=slug.replace("-", " ").title(),
        description=f"what {slug} concluded",
        type=TYPE_PROJECT,
        body=body,
        partition=_PARTITION,
        origins=(Origin(agent="claude-code", native_path=f"/old/{slug}.md", anchor=slug),),
        created_at=stamp,
        updated_at=stamp,
    )
    store.write_note(note)
    return note


# --- Store each note as one Markdown file with frontmatter --------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="write a note's frontmatter with a one-line description"
)
async def test_a_distilled_note_carries_the_full_frontmatter_and_a_one_line_description() -> None:
    _raw(
        "Lockfile",
        "Run uv sync --frozen.",
        description="Dependencies are locked with uv.\nA plain pip install drifts.",
    )

    await distil_partition(_PARTITION)

    files = sorted(paths.notes_dir(_PARTITION).iterdir())
    assert len(files) == 1 and files[0].suffix == ".md"
    text = files[0].read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, _, rest = text.partition("---\n")
    frontmatter_text, _, _ = rest.partition("\n---\n")
    frontmatter = yaml.safe_load(frontmatter_text)
    for key in ("title", "description", "type", "origins", "created_at", "updated_at"):
        assert key in frontmatter, key
    assert frontmatter["origins"] and frontmatter["origins"][0]["agent"] == "codex"
    assert frontmatter["created_at"] and frontmatter["updated_at"]
    assert frontmatter["type"] in NOTE_TYPES
    assert "\n" not in frontmatter["description"]
    assert frontmatter["description"] == (
        "Dependencies are locked with uv. A plain pip install drifts."
    )


# --- Keep notes readable as plain files ---------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="open a note from disk with no daemon running")
async def test_a_distilled_note_reads_as_plain_markdown_straight_off_disk() -> None:
    _raw("Lockfile", "Run `uv sync --frozen`; a plain pip install drifts.", description="uv lock")
    await distil_partition(_PARTITION)
    (note_file,) = list(paths.notes_dir(_PARTITION).glob("*.md"))

    # Only pathlib and a YAML parser from here on — no Coffer code at all.
    text = pathlib.Path(str(note_file)).read_text(encoding="utf-8")
    assert text.startswith("---\n")
    head, sep, body = text[len("---\n") :].partition("\n---\n")
    assert sep, "the frontmatter fence is closed"
    frontmatter = yaml.safe_load(head)
    assert frontmatter["title"] == "Lockfile"
    assert frontmatter["description"] == "uv lock"
    assert "Run `uv sync --frozen`; a plain pip install drifts." in body


# --- Write each index line to stand on its own --------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="state the source's search terms in the index line")
async def test_the_search_terms_appear_in_memory_md_and_the_context_in_one_order() -> None:
    resources = FakeResources()
    resources._row(kind=KIND_MEMORY, name="global", config={})
    service = memory_service(resources, {})

    _raw(
        "Plain preference",
        "prefers short replies",
        anchor="old",
        partition="global",
        type=TYPE_USER,
    )
    await distil_partition("global")
    _raw(
        "Daemon restart",
        "restart the daemon with stop/start",
        anchor="new",
        partition="global",
        type=TYPE_USER,
        search_terms=("coffer daemon", "port drift"),
    )
    await distil_partition("global")
    # A third, newest, of another type: the two surfaces interleave types by recency.
    _raw(
        "Reply tersely",
        "no trailing summaries",
        anchor="newest",
        partition="global",
        type=TYPE_FEEDBACK,
    )
    await distil_partition("global")

    notes = {n.title: n for n in store.list_notes("global")}
    newest, newer, older = (
        notes["Reply tersely"],
        notes["Daemon restart"],
        notes["Plain preference"],
    )
    assert newer.search_terms == ("coffer daemon", "port drift")
    assert older.search_terms == ()
    assert newer.updated_at > older.updated_at

    index_lines = [
        line
        for line in paths.index_path("global").read_text(encoding="utf-8").splitlines()
        if line.startswith("- **")
    ]
    composed = await compose_context(service, cwd="")
    context_lines = [line for line in composed.text.splitlines() if line.startswith("- **")]

    assert index_lines[1].endswith(" · look up: coffer daemon, port drift")
    assert "look up" not in index_lines[2]
    assert context_lines == index_lines
    assert context_lines == [index_line(newest), index_line(newer), index_line(older)]


# --- Confine reads to registered agents' memory paths -------------------------


@pytest.mark.parametrize("segment", ["..", "a/b", "../escape", "a\\b", ".hidden", ".raw"])
@pytest.mark.acceptance(
    spec="memory", scenario="refuse a path segment built from source contents that escapes"
)
def test_a_segment_taken_from_a_source_is_refused_rather_than_resolved(segment: str) -> None:
    root = paths.memory_root()

    with pytest.raises(UnsafeMemoryPath):
        paths.partition_dir(segment)
    with pytest.raises(UnsafeMemoryPath):
        paths.raw_path(_PARTITION, segment)
    # And through the writer aggregation uses: a partition name from a source
    # never reaches the disk.
    stored = StoredRawEntry(
        partition=segment,
        agent="codex",
        native_path="/native/codex.md",
        captured_at="2026-01-01T00:00:00+00:00",
        entry=RawEntry(
            title="t", description="d", type=TYPE_PROJECT, body="b", anchor="a", project_root=""
        ),
    )
    with pytest.raises(UnsafeMemoryPath):
        raw_store.write_raw_entry(stored)
    assert not root.exists() or not any(p.is_file() for p in root.rglob("*"))

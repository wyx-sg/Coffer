"""Acceptance scenarios for notes, the distil pass, the index and the read paths.

Every test drives the real store under the suite-pinned ``COFFER_MEMORY_ROOT``
and the real distil pass; the internal connection is always a fake that either
answers from a script or records what it was asked.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest
import yaml

from coffer.application.memory import distil_routing, distil_write
from coffer.application.memory.context import compose_context
from coffer.application.memory.distil import distil_partition
from coffer.application.memory.index import index_line
from coffer.application.memory.recall import RecallService
from coffer.application.memory.service import KIND_MEMORY
from coffer.domain.memory.note import NOTE_TYPES, TYPE_PROJECT, TYPE_USER, Note, Origin
from coffer.domain.memory.reader import RawEntry
from coffer.infrastructure.memory import paths, raw_store, store
from coffer.infrastructure.memory.paths import UnsafeMemoryPath
from coffer.infrastructure.memory.raw_store import StoredRawEntry, write_raw_entry
from tests.unit.memory.conftest import (
    ExplodingCompletion,
    FakeResources,
    NoModelSelector,
    StubModelSelector,
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


class _RecordingCompletion:
    """Answers routing requests with ``routing`` and writing requests from
    ``writes`` (keyed by the current note's title, ``""`` for a new note), and
    records every request it was sent."""

    def __init__(self, routing: str, writes: dict[str, str] | None = None) -> None:
        self._routing = routing
        self._writes = writes or {}
        self.routing_calls: list[dict[str, Any]] = []
        self.writing_calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: Any,
        credential_resolver: Any,
        timeout: float | None = None,
    ) -> str:
        payload = json.loads(user)
        if system == distil_routing.ROUTING_SYSTEM:
            self.routing_calls.append(payload)
            return self._routing
        assert system == distil_write.WRITE_SYSTEM
        self.writing_calls.append(payload)
        current = payload["current_note"]["title"]
        if current in self._writes:
            return self._writes[current]
        entry = payload["new_entries"][0]
        return json.dumps(
            {
                "title": current or entry["title"],
                "description": f"rewritten: {entry['description']}",
                "body": f"Coffer's own account of {entry['title']}.",
            }
        )


def _snapshot(directory: pathlib.Path) -> dict[str, tuple[bytes, float]]:
    return {
        str(p.relative_to(directory)): (p.read_bytes(), p.stat().st_mtime)
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


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

    await distil_partition(_PARTITION, completion=None, model_selector=NoModelSelector())

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


# --- Write notes in Coffer's own words ----------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="write the note body the distil model wrote")
async def test_the_note_body_is_the_models_rewrite_and_the_raw_entry_keeps_its_words() -> None:
    original = "the agent's own verbatim bullet about worktrees"
    entry = _raw("Worktrees", original)
    completion = _RecordingCompletion(
        json.dumps(
            {"actions": [{"entry": entry.entry_id, "action": "open", "title": "Worktrees"}]}
        ),
        writes={
            "": json.dumps(
                {
                    "title": "Worktrees",
                    "description": "Develop in a worktree",
                    "body": "Coffer's rewording: always develop in a git worktree.",
                }
            )
        },
    )

    await distil_partition(_PARTITION, completion=completion, model_selector=StubModelSelector())

    (note,) = store.list_notes(_PARTITION)
    assert note.body.strip() == "Coffer's rewording: always develop in a git worktree."
    assert original not in note.body
    assert raw_store.read_raw_entry(_PARTITION, entry.entry_id).entry.body == original
    assert [o.key for o in note.origins] == [entry.entry_id]


# --- Keep notes readable as plain files ---------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="open a note from disk with no daemon running")
async def test_a_distilled_note_reads_as_plain_markdown_straight_off_disk() -> None:
    _raw("Lockfile", "Run `uv sync --frozen`; a plain pip install drifts.", description="uv lock")
    await distil_partition(_PARTITION, completion=None, model_selector=NoModelSelector())
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


# --- Distil incrementally in two stages ---------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="route over the index and write only the touched notes"
)
async def test_routing_sees_index_lines_only_and_one_write_carries_one_body() -> None:
    bodies = {
        "daemon-restart": "BODY-daemon: restart with coffer daemon stop/start.",
        "uv-lockfile": "BODY-uv: dependencies are locked with uv.",
        "worktrees": "BODY-worktrees: always develop in a worktree.",
    }
    for slug, body in bodies.items():
        _existing_note(slug, body)
    entry = _raw("Frozen sync", "Use uv sync --frozen, never a bare sync.", anchor="frozen")
    completion = _RecordingCompletion(
        json.dumps(
            {"actions": [{"entry": entry.entry_id, "action": "merge", "slug": "uv-lockfile"}]}
        )
    )

    result = await distil_partition(
        _PARTITION, completion=completion, model_selector=StubModelSelector()
    )

    assert result.merged == 1
    (routing,) = completion.routing_calls
    assert [e["id"] for e in routing["entries"]] == [entry.entry_id]
    assert sorted(n["slug"] for n in routing["notes"]) == sorted(bodies)
    for note in routing["notes"]:
        assert set(note) == {"slug", "title", "description"}
    routing_text = json.dumps(routing)
    for body in bodies.values():
        assert body not in routing_text

    (writing,) = completion.writing_calls
    assert writing["current_note"]["body"] == bodies["uv-lockfile"]
    writing_text = json.dumps(writing)
    assert bodies["daemon-restart"] not in writing_text
    assert bodies["worktrees"] not in writing_text
    assert [e["title"] for e in writing["new_entries"]] == ["Frozen sync"]


# --- Keep distil out of the raw directory -------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="leave the raw directory byte-identical through a model-driven pass"
)
async def test_a_merge_an_open_and_a_retirement_leave_every_raw_file_untouched() -> None:
    _existing_note("uv-lockfile", "locked with uv")
    _existing_note("pip-install", "a plain pip install is fine")
    merge = _raw("Frozen", "use --frozen", anchor="a-merge")
    opened = _raw("Worktrees", "develop in a worktree", anchor="b-open")
    retire = _raw("No pip", "never run pip install here", anchor="c-retire")
    completion = _RecordingCompletion(
        json.dumps(
            {
                "actions": [
                    {"entry": merge.entry_id, "action": "merge", "slug": "uv-lockfile"},
                    {"entry": opened.entry_id, "action": "open", "title": "Worktrees"},
                    {
                        "entry": retire.entry_id,
                        "action": "retire",
                        "slug": "pip-install",
                        "reason": "pip install drifts",
                    },
                ]
            }
        )
    )
    raw_dir = paths.raw_dir(_PARTITION)
    before = _snapshot(raw_dir)
    assert len(before) == 3

    result = await distil_partition(
        _PARTITION, completion=completion, model_selector=StubModelSelector()
    )

    # The pass really did all three things the scenario names.
    assert (result.merged, result.opened, result.retired) == (1, 2, 1)
    assert not paths.note_path(_PARTITION, "pip-install").exists()
    assert _snapshot(raw_dir) == before
    assert sorted(p.name for p in raw_dir.iterdir()) == sorted(pathlib.Path(k).name for k in before)


# --- Record what each distil pass did -----------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer",
    [
        "Sure! Here is what I would do with these entries.",
        '{"actions": "merge everything"}',
        '["not", "an", "object"]',
        '{"actions": [{"entry": "no-such-entry", "action": "merge", "slug": "nope"}]}',
    ],
)
@pytest.mark.acceptance(
    spec="memory", scenario="survive malformed routing output and still write the index"
)
async def test_a_malformed_routing_answer_proposes_nothing_and_the_index_survives(
    answer: str,
) -> None:
    before = _existing_note("uv-lockfile", "locked with uv")
    _raw("Frozen", "use --frozen", anchor="one")
    _raw("Worktrees", "develop in a worktree", anchor="two")
    completion = _RecordingCompletion(answer)

    result = await distil_partition(
        _PARTITION, completion=completion, model_selector=StubModelSelector()
    )

    assert len(completion.routing_calls) == 1
    assert completion.writing_calls == []
    assert (result.merged, result.opened, result.retired, result.dropped) == (0, 0, 0, 0)
    assert store.list_notes(_PARTITION) == (before,)
    assert paths.index_path(_PARTITION).is_file()
    assert index_line(before) in paths.index_path(_PARTITION).read_text(encoding="utf-8")


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
    await distil_partition("global", completion=None, model_selector=NoModelSelector())
    _raw(
        "Daemon restart",
        "restart the daemon with stop/start",
        anchor="new",
        partition="global",
        type=TYPE_USER,
        search_terms=("coffer daemon", "port drift"),
    )
    await distil_partition("global", completion=None, model_selector=NoModelSelector())

    notes = {n.title: n for n in store.list_notes("global")}
    newer, older = notes["Daemon restart"], notes["Plain preference"]
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

    assert index_lines[0].endswith(" · look up: coffer daemon, port drift")
    assert "look up" not in index_lines[1]
    assert context_lines == index_lines
    assert context_lines == [index_line(newer), index_line(older)]


# --- Send content out only for distil -----------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="compose context and recall without calling any model"
)
async def test_context_and_recall_answer_while_the_internal_connection_would_fail() -> None:
    _raw("Lockfile", "dependencies are locked with uv", partition="global", type=TYPE_USER)
    await distil_partition("global", completion=None, model_selector=NoModelSelector())
    resources = FakeResources()
    resources._row(kind=KIND_MEMORY, name="global", config={})

    class _SelectorThatFails:
        async def get_default(self) -> Any:
            raise AssertionError("delivery and recall must not reach the internal connection")

    service = memory_service(
        resources, {}, completion=ExplodingCompletion(), model_selector=_SelectorThatFails()
    )

    composed = await compose_context(service, cwd="")
    recalled = await RecallService(memory=service).recall("locked with uv")

    assert "Lockfile" in composed.text
    assert [n.title for n in recalled.notes] == ["Lockfile"]


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

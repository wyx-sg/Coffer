"""The index: one line per note, rendered once for two readers (FR-029).

``MEMORY.md`` and the delivered payload must be the same lines in the same
order, because they were two renderings once and drifted — and under a ceiling
the sort order *is* which notes survive a trim (FR-030). So this file pins
three things: what a line says, what "newest" means, and that a line is
sufficient on its own.

Pure: ``index.py`` has no filesystem and no model, which is what guarantees
FR-024's path — an installation with no internal connection still gets a real
index because nothing here can depend on a model having run.
"""

from __future__ import annotations

from coffer.application.memory.index import index_line, recency, render_index
from coffer.domain.memory.note import (
    TYPE_FEEDBACK,
    TYPE_PROJECT,
    TYPE_USER,
    Note,
    Origin,
)


def _note(
    slug: str,
    *,
    title: str = "",
    description: str = "a description",
    type: str = TYPE_PROJECT,
    search_terms: tuple[str, ...] = (),
    created_at: str = "",
    updated_at: str = "",
    origins: tuple[Origin, ...] = (),
) -> Note:
    return Note(
        slug=slug,
        title=title if title != "" else slug.replace("-", " ").title(),
        description=description,
        type=type,
        body="the body, which never reaches a line",
        partition="coffer",
        origins=origins,
        created_at=created_at,
        updated_at=updated_at,
        search_terms=search_terms,
    )


# --- one line ----------------------------------------------------------------


def test_a_line_carries_the_title_the_file_name_and_the_conclusion() -> None:
    line = index_line(
        _note("worktree-development", title="Worktrees", description="No .venv — symlink it")
    )
    assert line == "- **Worktrees** (`worktree-development.md`) — No .venv — symlink it"


def test_a_line_states_the_sources_own_search_terms() -> None:
    """Codex answers "what would you look this up by" itself (FR-004);
    discarding that answer is what left retrieval to guesswork."""
    line = index_line(_note("daemon-restart", search_terms=("daemon", "port drift")))
    assert line.endswith(" · look up: daemon, port drift")


def test_a_line_never_carries_the_body() -> None:
    note = _note("n", description="short")
    assert note.body not in index_line(note)


def test_a_multi_line_description_is_folded_onto_one_line() -> None:
    line = index_line(_note("n", description="first\n  second\tthird"))
    assert line == "- **N** (`n.md`) — first second third"


def test_a_note_that_lost_its_title_is_named_by_its_slug() -> None:
    assert index_line(_note("some-slug", title="   ")).startswith(
        "- **some-slug** (`some-slug.md`)"
    )


def test_a_note_with_no_description_is_still_one_line() -> None:
    assert index_line(_note("n", description="")) == "- **N** (`n.md`)"


def test_blank_search_terms_are_not_rendered_as_an_empty_list() -> None:
    assert " · look up:" not in index_line(_note("n", search_terms=("", "   ")))


# --- one definition of "newest" ----------------------------------------------


def test_recency_prefers_the_notes_own_timestamps() -> None:
    note = _note("n", created_at="2026-01-01", updated_at="2026-06-01")
    assert recency(note) == "2026-06-01"


def test_a_note_dated_only_at_its_source_still_sorts_by_that_date() -> None:
    """The exact drift FR-029 names: delivery read ``captured_at`` alone, so a
    note timestamped only by its origin scored ``""`` and sorted last there
    while sorting correctly in the file."""
    note = _note(
        "n",
        origins=(
            Origin(agent="codex", native_path="/a", captured_at="2026-03-01"),
            Origin(agent="codex", native_path="/b", source_written_at="2026-04-01"),
        ),
    )
    assert recency(note) == "2026-04-01"


def test_a_note_with_no_timestamp_anywhere_sorts_last_rather_than_raising() -> None:
    assert recency(_note("n")) == ""


# --- the whole file ----------------------------------------------------------


def test_the_index_restates_the_repository_the_partition_is_about() -> None:
    """A partition's directory name is a slug and it collects a repository's
    worktrees and clones, so "which project is this?" needs an answer (FR-014)."""
    text = render_index([_note("n")], partition="coffer", repository_path="/home/dev/coffer")
    assert "# coffer — Coffer memory" in text
    assert "`/home/dev/coffer`" in text
    assert "notes/" in text


def test_global_says_it_is_about_the_developer_rather_than_a_repository() -> None:
    text = render_index([_note("n", type=TYPE_USER)], partition="global", repository_path="")
    assert "What is known about the developer" in text


def test_an_empty_partition_still_renders_an_index() -> None:
    text = render_index([], partition="coffer", repository_path="/home/dev/coffer")
    assert "No notes yet." in text


def test_notes_are_grouped_project_first_then_the_personal_types() -> None:
    text = render_index(
        [
            _note("u", type=TYPE_USER),
            _note("f", type=TYPE_FEEDBACK),
            _note("p", type=TYPE_PROJECT),
        ],
        partition="coffer",
        repository_path="/r",
    )
    headings = [line for line in text.split("\n") if line.startswith("## ")]
    assert headings == [
        "## Project",
        "## About the developer",
        "## Feedback and standing instructions",
    ]


def test_a_stray_type_is_rendered_after_the_known_ones_rather_than_dropped() -> None:
    text = render_index(
        [_note("p", type=TYPE_PROJECT), _note("odd", type="invented")],
        partition="coffer",
        repository_path="/r",
    )
    assert "`odd.md`" in text
    assert text.index("## Project") < text.index("## invented")


def test_within_a_group_the_newest_note_is_listed_first() -> None:
    text = render_index(
        [
            _note("older", updated_at="2026-01-01"),
            _note("newest", updated_at="2026-09-01"),
            _note("middle", updated_at="2026-05-01"),
        ],
        partition="coffer",
        repository_path="/r",
    )
    body = text.split("## Project\n", 1)[1]
    assert [line.split("(`")[1].split(".md")[0] for line in body.strip().split("\n") if line] == [
        "newest",
        "middle",
        "older",
    ]


def test_the_file_uses_the_same_line_function_the_delivery_does() -> None:
    note = _note("shared-renderer", search_terms=("term",))
    text = render_index([note], partition="coffer", repository_path="/r")
    assert index_line(note) in text.split("\n")

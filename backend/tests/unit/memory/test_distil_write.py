"""Stage two: Coffer's own words for one note (FR-020).

One request per note the routing stage actually touched, carrying **that one
note's** current text and the entries routed to it — which is the whole reason
routing was a separate stage.

``description`` is the product. It is not a summary of the note, it is the
index entry, and the index is the whole of what a session is given
(FR-017, FR-029) — so a half-written note is worse than no note, and every
unusable answer returns ``None`` rather than something partial.
"""

from __future__ import annotations

import json

import pytest

from coffer.application.memory import distil_write as writing
from coffer.domain.memory.note import TYPE_PROJECT, Note, Origin
from coffer.domain.memory.reader import RawEntry
from coffer.infrastructure.memory.raw_store import StoredRawEntry


def _entry(body: str, *, agent: str = "codex") -> StoredRawEntry:
    return StoredRawEntry(
        partition="coffer",
        agent=agent,
        native_path=f"/native/{agent}.md",
        captured_at="2026-01-01",
        entry=RawEntry(
            title="a handle",
            description="a description",
            type=TYPE_PROJECT,
            body=body,
            anchor="x",
            project_root="/home/dev/coffer",
        ),
    )


def _existing() -> Note:
    return Note(
        slug="worktree-trap",
        title="Worktree trap",
        description="the conclusion so far",
        type=TYPE_PROJECT,
        body="what the note already says",
        partition="coffer",
        origins=(Origin(agent="codex", native_path="/old.md", anchor="x"),),
    )


def test_the_request_carries_one_notes_text_and_the_entries_routed_to_it() -> None:
    payload = json.loads(
        writing.write_payload([_entry("new material")], existing=_existing(), partition="coffer")
    )

    assert payload["current_note"] == {
        "title": "Worktree trap",
        "description": "the conclusion so far",
        "body": "what the note already says",
    }
    assert payload["new_entries"] == [
        {
            "agent": "codex",
            "title": "a handle",
            "description": "a description",
            "text": "new material",
        }
    ]


def test_a_new_note_arrives_as_an_empty_current_note() -> None:
    payload = json.loads(writing.write_payload([_entry("m")], existing=None, partition="coffer"))
    assert payload["current_note"] == {"title": "", "description": "", "body": ""}


def test_an_entrys_whole_text_travels_here_unlike_routings_capped_copy() -> None:
    """This is where the content actually lands; truncating it would silently
    drop the detail the pass exists to carry."""
    long_body = "x" * 8000
    payload = json.loads(
        writing.write_payload([_entry(long_body)], existing=None, partition="coffer")
    )
    assert payload["new_entries"][0]["text"] == long_body


def test_the_prompt_asks_for_the_conclusion_in_the_description() -> None:
    assert "It is the INDEX" in writing.WRITE_SYSTEM
    assert "your own words" in writing.WRITE_SYSTEM.lower()


def test_a_usable_answer_becomes_the_three_fields_the_model_may_set() -> None:
    written = writing.parse_written(
        json.dumps(
            {
                "title": "  Worktree trap  ",
                "description": "worktrees have no .venv,\n  symlink the main one",
                "body": "  The note body.  ",
            }
        )
    )

    assert written is not None
    assert written.title == "Worktree trap"
    # One line, always: a newline here would break the one-note-per-line shape
    # both ``MEMORY.md`` and the delivered payload depend on.
    assert written.description == "worktrees have no .venv, symlink the main one"
    assert written.body == "The note body.\n"
    assert set(vars(written)) == {"title", "description", "body"}


@pytest.mark.parametrize(
    "answer",
    [
        "not json",
        json.dumps({"title": "T", "description": "d"}),
        json.dumps({"title": "T", "description": "d", "body": "   "}),
        json.dumps({"title": "   ", "description": "d", "body": "a body"}),
        json.dumps({"title": 7, "description": "d", "body": "a body"}),
        json.dumps({}),
    ],
)
def test_an_unusable_answer_writes_nothing_rather_than_half_a_note(answer: str) -> None:
    assert writing.parse_written(answer) is None


def test_a_missing_description_still_yields_a_note_rather_than_none() -> None:
    """The title and body are what make a file worth writing; a thin index
    line is a smaller loss than losing the note."""
    written = writing.parse_written(json.dumps({"title": "T", "body": "a body"}))
    assert written is not None
    assert written.description == ""


@pytest.mark.asyncio
async def test_a_failing_completion_returns_none_rather_than_raising() -> None:
    class _Broken:
        async def complete(self, **kw: object) -> str:
            raise RuntimeError("the provider is down")

    result = await writing.rewrite_note(
        [_entry("m")],
        existing=None,
        partition="coffer",
        model="m",
        completion=_Broken(),  # type: ignore[arg-type]
        credential_resolver=lambda ref: ref,
    )

    assert result is None


@pytest.mark.asyncio
async def test_a_rewritten_note_comes_back_from_the_model_it_was_asked_of() -> None:
    class _Scripted:
        def __init__(self) -> None:
            self.user = ""

        async def complete(
            self,
            *,
            system: str,
            user: str,
            model: object,
            credential_resolver: object,
            timeout: float | None = None,
        ) -> str:
            self.user = user
            return json.dumps({"title": "T", "description": "d", "body": "Coffer's own prose."})

    completion = _Scripted()
    result = await writing.rewrite_note(
        [_entry("new material")],
        existing=_existing(),
        partition="coffer",
        model="m",
        completion=completion,  # type: ignore[arg-type]
        credential_resolver=lambda ref: ref,
    )

    assert result is not None
    assert result.body == "Coffer's own prose.\n"
    assert "new material" in completion.user

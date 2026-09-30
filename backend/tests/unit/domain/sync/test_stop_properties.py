"""Properties of a stopped round and its answers (ADR
sync-applies-clean-merges-and-stops-on-any-conflict; spec vault-sync "Answer
each conflicting file and continue the round").

A stop survives being written to ``local/sync/round.json`` and read back; it
continues only once every file has an answer, in any order; an answer names
one of the stop's files or is refused; and each answer puts exactly the blob
it chose at the file's path.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("hypothesis")

from hypothesis import given
from hypothesis import strategies as st

from coffer.domain.sync.breaker import Breach
from coffer.domain.sync.stops import (
    Answer,
    ConflictFile,
    ConflictReason,
    Hold,
    HoldDirection,
    Stop,
    StopKind,
    stop_from_json,
    to_json,
)

_BLOB = st.text("0123456789abcdef", min_size=40, max_size=40)
_PATH = st.builds(
    lambda area, name: f"{area}/{name}.md",
    st.sampled_from(("knowledge", "skills", "memory-triggers")),
    st.text("abcdefghij", min_size=1, max_size=8),
)
_TIME = st.none() | st.just("2026-10-01T09:30:00+00:00")


@st.composite
def _conflict(draw: st.DrawFn, path: str) -> ConflictFile:
    answer = draw(st.none() | st.sampled_from(Answer))
    return ConflictFile(
        path=path,
        area=path.split("/", 1)[0],
        reason=draw(st.sampled_from(ConflictReason)),
        ours=draw(st.none() | _BLOB),
        theirs=draw(st.none() | _BLOB),
        base=draw(st.none() | _BLOB),
        ours_time=draw(_TIME),
        theirs_time=draw(_TIME),
        theirs_machine=draw(st.none() | st.just("Mac mini")),
        other_path=draw(st.none() | _PATH),
        answer=answer,
        edited=draw(_BLOB) if answer is Answer.EDITED else None,
    )


@st.composite
def stops(draw: st.DrawFn) -> Stop:
    kind = draw(st.sampled_from(StopKind))
    paths = draw(st.lists(_PATH, unique=True, max_size=12))
    conflicts = tuple(draw(_conflict(p)) for p in paths) if kind is StopKind.CONFLICTS else ()
    hold = (
        Hold(
            direction=draw(st.sampled_from(HoldDirection)),
            breaches=tuple(
                Breach(area, draw(st.integers(1, 50)), draw(st.integers(0, 500)))
                for area in draw(st.sets(st.sampled_from(("knowledge", "skills")), min_size=1))
            ),
            paths=tuple(sorted(paths)),
        )
        if kind is StopKind.HOLD
        else None
    )
    return Stop(
        kind=kind,
        local=draw(_BLOB),
        remote=draw(_BLOB),
        base=draw(st.none() | _BLOB),
        raised_at="2026-10-01T09:30:00+00:00",
        conflicts=conflicts,
        hold=hold,
        tree=draw(st.none() | _BLOB),
        join=draw(st.none() | _BLOB),
    )


@given(stops())
def test_a_stop_reads_back_as_it_was_written(stop: Stop) -> None:
    # Through real JSON text, as round.json holds it.
    assert stop_from_json(json.loads(json.dumps(to_json(stop)))) == stop


@st.composite
def _unanswered_and_order(draw: st.DrawFn) -> tuple[Stop, list[tuple[str, Answer]]]:
    paths = draw(st.lists(_PATH, unique=True, min_size=1, max_size=12))
    stop = Stop(
        kind=StopKind.CONFLICTS,
        local="l" * 40,
        remote="r" * 40,
        base=None,
        raised_at="2026-10-01T09:30:00+00:00",
        conflicts=tuple(
            ConflictFile(p, p.split("/", 1)[0], ConflictReason.BOTH_CHANGED, "o" * 40, "t" * 40)
            for p in paths
        ),
    )
    answers = [(p, draw(st.sampled_from((Answer.MINE, Answer.THEIRS)))) for p in paths]
    return stop, draw(st.permutations(answers))


@given(_unanswered_and_order())
def test_a_stop_continues_only_once_every_file_is_answered_in_any_order(
    case: tuple[Stop, list[tuple[str, Answer]]],
) -> None:
    stop, answers = case
    for i, (path, answer) in enumerate(answers):
        assert len(stop.unanswered) == len(answers) - i
        stop = stop.with_answer(path, answer)
    assert stop.unanswered == ()
    chosen = {c.path: c.answer for c in stop.conflicts}
    assert chosen == dict(answers)
    # The files keep the order git reported them in, whatever the answering order.
    assert [c.path for c in stop.conflicts] == [c.path for c in case[0].conflicts]


@given(stops(), _PATH)
def test_an_answer_for_a_file_the_stop_does_not_name_is_refused(stop: Stop, path: str) -> None:
    if any(c.path == path for c in stop.conflicts):
        return
    with pytest.raises(KeyError):
        stop.with_answer(path, Answer.MINE)


@given(
    st.builds(
        ConflictFile,
        _PATH,
        st.just("knowledge"),
        st.sampled_from(ConflictReason),
        st.none() | _BLOB,
        st.none() | _BLOB,
    ),
    st.sampled_from(Answer),
    _BLOB,
)
def test_each_answer_puts_the_blob_it_chose_at_the_path(
    conflict: ConflictFile, answer: Answer, edited: str
) -> None:
    with pytest.raises(ValueError):
        _ = conflict.chosen_blob  # no answer yet
    answered = conflict.answered(answer, edited if answer is Answer.EDITED else None)
    expected = {Answer.MINE: conflict.ours, Answer.THEIRS: conflict.theirs, Answer.EDITED: edited}
    assert answered.chosen_blob == expected[answer]

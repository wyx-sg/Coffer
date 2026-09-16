"""The organise pass: a structured completion over one partition's facts.

``COFFER_MEMORY_ROOT`` is pinned to ``tmp_path`` by the suite-wide
``_isolated_memory_root`` fixture (``backend/tests/conftest.py``), so every
test here reads and writes real files under a throwaway directory — never a
developer's actual ``~/.coffer/memory``. The completion port is always a
fake; nothing here calls a real model (unit-tier purity).
"""

from __future__ import annotations

import json

import pytest

from coffer.application.memory.organise import organise_partition
from coffer.domain.memory.fact import (
    STATUS_ACTIVE,
    STATUS_SUPERSEDED,
    TYPE_FEEDBACK,
    TYPE_PROJECT,
    Fact,
    Origin,
)
from coffer.infrastructure.memory import paths, store

_PARTITION = "coffer"


def _fact(
    *,
    slug: str,
    native_path: str = "/native/default.md",
    title: str = "A fact",
    body: str = "The source's own words.",
    type: str = TYPE_PROJECT,
) -> Fact:
    return Fact(
        slug=slug,
        title=title,
        description=f"description of {title}",
        type=type,
        body=body,
        partition=_PARTITION,
        origins=(Origin(agent="claude_code", native_path=native_path),),
    )


class _NoModel:
    async def get_default(self):  # type: ignore[no-untyped-def]
        return None


class _Model:
    def __init__(self, connection) -> None:  # type: ignore[no-untyped-def]
        self._connection = connection

    async def get_default(self):  # type: ignore[no-untyped-def]
        return self._connection


class _FakeCompletion:
    """Returns queued responses in order; ``"{}"`` once the queue is empty."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def complete(self, *, system, user, model, credential_resolver):  # type: ignore[no-untyped-def]
        self.calls.append({"system": system, "user": user, "model": model})
        return self._responses.pop(0) if self._responses else "{}"


class _FailIfCalledCompletion:
    def __init__(self) -> None:
        self.called = False

    async def complete(self, *, system, user, model, credential_resolver):  # type: ignore[no-untyped-def]
        self.called = True
        raise AssertionError("completion must not be called with no internal connection")


@pytest.fixture
def fake_connection():  # type: ignore[no-untyped-def]
    from coffer.domain.provider.config import ProviderConfig, ResolvedConnection

    return ResolvedConnection(
        config=ProviderConfig(
            protocol="openai",
            base_url="https://example.invalid/v1",
            credential_ref="provider/test",
        ),
        model="agnes-2.0-flash",
    )


async def test_duplicate_pair_becomes_one_fact_with_both_origins(fake_connection) -> None:  # type: ignore[no-untyped-def]
    fact_a = _fact(slug="a", native_path="/native/a.md")
    fact_b = _fact(slug="b", native_path="/native/b.md", title="Different words, same fact")
    store.write_fact(fact_a)
    store.write_fact(fact_b)
    completion = _FakeCompletion([json.dumps({"duplicates": [[fact_a.key, fact_b.key]]})])

    result = await organise_partition(
        _PARTITION,
        models=_Model(fake_connection),
        completion=completion,
        credential_resolver=lambda ref: "k",
    )

    assert result.merged == 1
    assert result.model_used is True
    a, b = store.read_fact(_PARTITION, "a"), store.read_fact(_PARTITION, "b")
    active, superseded = (a, b) if a.status == STATUS_ACTIVE else (b, a)
    assert superseded.status == STATUS_SUPERSEDED
    assert superseded.superseded_by == active.key
    assert {o.native_path for o in active.origins} == {"/native/a.md", "/native/b.md"}


async def test_supersede_proposal_marks_the_older_fact(fake_connection) -> None:  # type: ignore[no-untyped-def]
    fact_a = _fact(slug="a", native_path="/native/a.md", title="Old decision")
    fact_b = _fact(slug="b", native_path="/native/b.md", title="New decision")
    store.write_fact(fact_a)
    store.write_fact(fact_b)
    completion = _FakeCompletion(
        [json.dumps({"supersedes": [{"older": fact_a.key, "newer": fact_b.key}]})]
    )

    result = await organise_partition(
        _PARTITION,
        models=_Model(fake_connection),
        completion=completion,
        credential_resolver=lambda ref: "k",
    )

    assert result.superseded == 1
    older = store.read_fact(_PARTITION, "a")
    assert older.status == STATUS_SUPERSEDED
    assert older.superseded_by == fact_b.key
    newer = store.read_fact(_PARTITION, "b")
    assert newer.status == STATUS_ACTIVE


@pytest.mark.acceptance(
    spec="memory",
    scenario="two facts with opposite conclusions are reported as a conflict",
)
async def test_conflict_is_flagged_on_both_sides(fake_connection) -> None:  # type: ignore[no-untyped-def]
    fact_a = _fact(slug="a", native_path="/native/a.md", title="Says X")
    fact_b = _fact(slug="b", native_path="/native/b.md", title="Says not X")
    store.write_fact(fact_a)
    store.write_fact(fact_b)
    completion = _FakeCompletion([json.dumps({"conflicts": [[fact_a.key, fact_b.key]]})])

    result = await organise_partition(
        _PARTITION,
        models=_Model(fake_connection),
        completion=completion,
        credential_resolver=lambda ref: "k",
    )

    assert result.conflicts == 1
    a, b = store.read_fact(_PARTITION, "a"), store.read_fact(_PARTITION, "b")
    assert a.conflicts_with == (fact_b.key,)
    assert b.conflicts_with == (fact_a.key,)


async def test_malformed_json_yields_no_proposals_and_does_not_raise(fake_connection) -> None:  # type: ignore[no-untyped-def]
    fact_a = _fact(slug="a")
    store.write_fact(fact_a)
    completion = _FakeCompletion(["not json at all {"])

    result = await organise_partition(
        _PARTITION,
        models=_Model(fake_connection),
        completion=completion,
        credential_resolver=lambda ref: "k",
    )

    assert (result.merged, result.superseded, result.conflicts) == (0, 0, 0)
    assert store.read_fact(_PARTITION, "a") == fact_a


async def test_a_proposal_naming_an_unknown_key_is_dropped(fake_connection) -> None:  # type: ignore[no-untyped-def]
    fact_a = _fact(slug="a")
    store.write_fact(fact_a)
    completion = _FakeCompletion([json.dumps({"duplicates": [["does-not-exist", fact_a.key]]})])

    result = await organise_partition(
        _PARTITION,
        models=_Model(fake_connection),
        completion=completion,
        credential_resolver=lambda ref: "k",
    )

    assert result.merged == 0
    assert store.read_fact(_PARTITION, "a") == fact_a


async def test_prose_instead_of_json_degrades_cleanly(fake_connection) -> None:  # type: ignore[no-untyped-def]
    fact_a = _fact(slug="a")
    store.write_fact(fact_a)
    completion = _FakeCompletion(
        ["Sure! Looking at these, I don't see anything worth flagging here."]
    )

    result = await organise_partition(
        _PARTITION,
        models=_Model(fake_connection),
        completion=completion,
        credential_resolver=lambda ref: "k",
    )

    assert (result.merged, result.superseded, result.conflicts) == (0, 0, 0)


@pytest.mark.acceptance(
    spec="memory", scenario="organise regenerates the summary without an internal connection"
)
async def test_organize_regenerates_the_summary_without_an_internal_connection() -> None:
    fact_a = _fact(slug="a", title="Only fact")
    store.write_fact(fact_a)
    completion = _FailIfCalledCompletion()

    result = await organise_partition(
        _PARTITION,
        models=_NoModel(),
        completion=completion,
        credential_resolver=lambda ref: "k",
    )

    assert result.model_used is False
    assert (result.merged, result.superseded, result.conflicts) == (0, 0, 0)
    assert completion.called is False
    summary = paths.summary_path(_PARTITION).read_text(encoding="utf-8")
    assert "Only fact" in summary
    # Nothing about the fact itself changed by an organise pass with no model.
    assert store.read_fact(_PARTITION, "a") == fact_a


async def test_digest_is_written_grouped_by_type(fake_connection) -> None:  # type: ignore[no-untyped-def]
    store.write_fact(
        _fact(slug="a", native_path="/native/a.md", type=TYPE_PROJECT, title="Proj fact")
    )
    store.write_fact(
        _fact(slug="b", native_path="/native/b.md", type=TYPE_FEEDBACK, title="Feedback fact")
    )
    completion = _FakeCompletion(["{}"])

    await organise_partition(
        _PARTITION,
        models=_Model(fake_connection),
        completion=completion,
        credential_resolver=lambda ref: "k",
    )

    summary = paths.summary_path(_PARTITION).read_text(encoding="utf-8")
    assert "Proj fact" in summary
    assert "Feedback fact" in summary
    assert summary.index("Proj fact") < summary.index("Feedback fact")


async def test_a_large_partition_is_chunked(fake_connection) -> None:  # type: ignore[no-untyped-def]
    for i in range(5):
        store.write_fact(_fact(slug=f"f{i}", native_path=f"/native/{i}.md", title=f"Fact {i}"))
    completion = _FakeCompletion(["{}", "{}", "{}"])

    result = await organise_partition(
        _PARTITION,
        models=_Model(fake_connection),
        completion=completion,
        credential_resolver=lambda ref: "k",
        max_facts_per_chunk=2,
    )

    assert result.model_used is True
    assert len(completion.calls) == 3
    sizes = [len(json.loads(call["user"])) for call in completion.calls]
    assert sizes == [2, 2, 1]


async def test_nothing_is_deleted_and_no_body_is_edited(fake_connection) -> None:  # type: ignore[no-untyped-def]
    fact_a = _fact(slug="a", native_path="/native/a.md", body="Body A, verbatim.")
    fact_b = _fact(
        slug="b",
        native_path="/native/b.md",
        title="Different words, same fact",
        body="Body B, verbatim.",
    )
    store.write_fact(fact_a)
    store.write_fact(fact_b)
    completion = _FakeCompletion([json.dumps({"duplicates": [[fact_a.key, fact_b.key]]})])

    await organise_partition(
        _PARTITION,
        models=_Model(fake_connection),
        completion=completion,
        credential_resolver=lambda ref: "k",
    )

    assert {p.stem for p in paths.facts_dir(_PARTITION).glob("*.md")} == {"a", "b"}
    assert store.read_fact(_PARTITION, "a").body == "Body A, verbatim."
    assert store.read_fact(_PARTITION, "b").body == "Body B, verbatim."

"""Unit tests for `coffer.infrastructure.memory.delivery_state` — the
last-fired record (spec memory FR-055).

Real `tmp_path` filesystem access, no database — same tier as
`test_store.py`/`test_paths.py`. `COFFER_MEMORY_ROOT` is pinned to a fresh
`tmp_path` by the suite-wide `_isolated_memory_root` fixture
(`backend/tests/conftest.py`), so this can never reach a developer's real
`~/.coffer/memory`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.infrastructure.memory import delivery_state, paths


def test_last_fired_at_is_empty_when_never_recorded() -> None:
    assert delivery_state.last_fired_at("cc") == ""


def test_record_fired_then_last_fired_at_reflects_it() -> None:
    delivery_state.record_fired("cc", now=datetime(2026, 9, 13, 12, 0, tzinfo=UTC))
    assert delivery_state.last_fired_at("cc") == "2026-09-13T12:00:00+00:00"


def test_record_fired_is_per_agent() -> None:
    delivery_state.record_fired("cc", now=datetime(2026, 9, 13, tzinfo=UTC))
    assert delivery_state.last_fired_at("codex") == ""
    assert delivery_state.last_fired_at("cc") != ""


def test_record_fired_overwrites_the_previous_timestamp() -> None:
    delivery_state.record_fired("cc", now=datetime(2026, 1, 1, tzinfo=UTC))
    delivery_state.record_fired("cc", now=datetime(2026, 9, 13, tzinfo=UTC))
    assert delivery_state.last_fired_at("cc") == "2026-09-13T00:00:00+00:00"


def test_state_file_lives_under_memory_root_and_is_dot_prefixed() -> None:
    delivery_state.record_fired("cc", now=datetime(2026, 1, 1, tzinfo=UTC))
    expected = paths.memory_root() / ".delivery_state.json"
    assert expected.is_file()


def test_load_tolerates_a_missing_file() -> None:
    assert delivery_state.load() == {}


def test_load_tolerates_a_corrupt_file() -> None:
    path = paths.memory_root() / delivery_state.STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json", encoding="utf-8")
    assert delivery_state.load() == {}


def test_load_tolerates_a_non_object_json_file() -> None:
    path = paths.memory_root() / delivery_state.STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert delivery_state.load() == {}

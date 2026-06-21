# backend/tests/unit/memory/test_lane.py
"""Unit: the four-lane taxonomy enum."""

from __future__ import annotations

from coffer.domain.memory.lane import Lane


def test_lane_values_are_the_four_folder_names() -> None:
    assert {lane.value for lane in Lane} == {"knowledge", "rules", "journal", "handoff"}


def test_lane_is_a_str() -> None:
    # StrEnum members compare equal to their string value (used as folder names).
    assert Lane.JOURNAL == "journal"
    assert f"{Lane.KNOWLEDGE}" == "knowledge"

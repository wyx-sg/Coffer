"""Version numbers: read from ``--version`` output, compared by their numbers."""

from __future__ import annotations

import pytest

from coffer.domain.agent.detection import parse_version as agent_parse_version
from coffer.domain.versions import at_least, compare_versions, parse_version, version_numbers


def test_agent_detection_still_exports_the_same_parser() -> None:
    assert agent_parse_version is parse_version


@pytest.mark.parametrize(
    ("output", "version"),
    [
        ("gh version 2.30.0 (2023-05-01)", "2.30.0"),
        ("jq-1.7.1", "1.7.1"),
        ("uv 0.4.18 (Homebrew 2024-09-01)", "0.4.18"),
        ("no number here", None),
    ],
)
def test_parse_version(output: str, version: str | None) -> None:
    assert parse_version(output) == version


def test_version_numbers() -> None:
    assert version_numbers("0.4.18") == (0, 4, 18)
    assert version_numbers("v2.40-rc1") == (2, 40)
    assert version_numbers("unknown") is None


@pytest.mark.parametrize(
    ("a", "b", "order"),
    [
        ("2.30", "2.40", -1),
        ("2.40", "2.4", 1),
        ("0.4", "0.4.0", 0),
        ("0.4.18", "0.4", 1),
        ("10.0", "9.9", 1),
    ],
)
def test_compare_versions(a: str, b: str, order: int) -> None:
    assert compare_versions(a, b) == order


def test_at_least_is_unknown_when_a_version_cannot_be_read() -> None:
    assert at_least("0.4.18", "0.4") is True
    assert at_least("2.30.0", "2.40") is False
    assert at_least("dev", "2.40") is None

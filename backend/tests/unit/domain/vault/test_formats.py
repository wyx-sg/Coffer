"""Per-file format versions and upgrade chains (coffer.domain.vault.formats)."""

from __future__ import annotations

from typing import Any

import pytest

from coffer.domain.vault.formats import (
    FormatSpec,
    FormatStatus,
    UpgradeStep,
    read,
    stamp,
)


def _rename_cmd(doc: dict[str, Any]) -> dict[str, Any]:
    doc["command"] = doc.pop("cmd", None)
    return doc


def _add_timeout(doc: dict[str, Any]) -> dict[str, Any]:
    doc.setdefault("timeout", None)
    return doc


SPEC = FormatSpec(
    current=3,
    steps=(
        UpgradeStep(1, _rename_cmd, additive=False),
        UpgradeStep(2, _add_timeout, additive=True),
    ),
)


def test_a_current_file_reads_as_current_and_is_writable() -> None:
    got = read({"format_version": 3, "command": "x"}, SPEC)
    assert got.status is FormatStatus.CURRENT and got.status.writable


@pytest.mark.acceptance(spec="vault-storage", scenario="an older file is upgraded in memory only")
def test_an_older_file_is_upgraded_in_memory_only() -> None:
    raw = {"format_version": 1, "cmd": "x"}
    got = read(raw, SPEC)
    assert got.status is FormatStatus.OLDER and not got.status.writable
    assert got.doc == {"format_version": 3, "command": "x", "timeout": None}
    assert raw == {"format_version": 1, "cmd": "x"}


def test_every_step_is_deterministic() -> None:
    raw = {"format_version": 1, "cmd": "x"}
    assert read(raw, SPEC).doc == read(dict(raw), SPEC).doc


@pytest.mark.acceptance(spec="vault-storage", scenario="a newer file is read-only here")
def test_a_newer_additive_file_is_readable_but_read_only() -> None:
    got = read({"format_version": 4, "format_compat": 3, "extra": 1}, SPEC)
    assert got.status is FormatStatus.NEWER_READABLE and not got.status.writable
    assert got.doc["extra"] == 1


def test_a_newer_file_that_names_no_compat_is_unreadable() -> None:
    assert read({"format_version": 4}, SPEC).status is FormatStatus.NEWER_UNREADABLE


def test_a_file_without_a_version_is_version_one() -> None:
    assert read({"cmd": "x"}, SPEC).status is FormatStatus.OLDER


def test_stamp_writes_the_compat_an_additive_step_allows() -> None:
    assert stamp({}, SPEC) == {"format_version": 3, "format_compat": 2}
    assert stamp({"format_compat": 1}, FormatSpec(current=1)) == {"format_version": 1}


def test_a_chain_with_a_gap_is_refused() -> None:
    with pytest.raises(ValueError, match="upgrade chain"):
        FormatSpec(current=3, steps=(UpgradeStep(2, _add_timeout, additive=True),))

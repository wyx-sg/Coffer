"""The retired transcript summary cache is removed once, and only that."""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.agent.legacy_cleanup import remove_transcript_sidecar


def test_the_leftover_cache_directory_is_removed_and_siblings_stay(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    cache = tmp_path / ".coffer" / "derived" / "cache"
    legacy = cache / "agent"
    legacy.mkdir(parents=True)
    (legacy / ".transcript_summaries.json").write_text("{}", encoding="utf-8")
    (cache / "other").mkdir()

    remove_transcript_sidecar()
    remove_transcript_sidecar()  # idempotent

    assert not legacy.exists()
    assert (cache / "other").is_dir()

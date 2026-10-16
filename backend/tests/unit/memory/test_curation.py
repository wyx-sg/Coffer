"""Each agent's own curation as Coffer reads it, and **Turn on** for Claude
Code's Auto Dream (spec memory "Show each agent's own curation and ask it to
curate now")."""

from __future__ import annotations

import json
import os
import pathlib

import pytest

from coffer.infrastructure.memory.curation import curation_state, enable_curation
from coffer.infrastructure.vault.home import config_backups_dir


def _claude(tmp_path: pathlib.Path, settings: dict[str, object] | None = None) -> pathlib.Path:
    config = tmp_path / ".claude"
    config.mkdir()
    if settings is not None:
        (config / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    return config


def _cache(tmp_path: pathlib.Path, enabled: bool) -> None:
    features = {"tengu_onyx_plover": {"enabled": enabled, "minHours": 24}}
    (tmp_path / ".claude.json").write_text(
        json.dumps({"cachedGrowthBookFeatures": features}), encoding="utf-8"
    )


def test_the_settings_key_decides_auto_dream(tmp_path: pathlib.Path) -> None:
    config = _claude(tmp_path, {"autoDreamEnabled": True})
    _cache(tmp_path, False)

    state = curation_state("claude_code", str(config))

    assert (state.memory, state.curation, state.source) == ("on", "on", "setting")


def test_without_the_key_the_account_default_decides(tmp_path: pathlib.Path) -> None:
    config = _claude(tmp_path, {})
    _cache(tmp_path, False)

    state = curation_state("claude_code", str(config))

    assert (state.curation, state.source) == ("off", "default")


def test_with_neither_auto_dream_is_unknown(tmp_path: pathlib.Path) -> None:
    config = _claude(tmp_path)

    assert curation_state("claude_code", str(config)).curation == "unknown"


def test_the_newest_lock_says_when_it_last_ran(tmp_path: pathlib.Path) -> None:
    config = _claude(tmp_path)
    for name, when in (("-a", 1_760_000_000), ("-b", 1_760_500_000)):
        memory = config / "projects" / name / "memory"
        memory.mkdir(parents=True)
        lock = memory / ".consolidate-lock"
        lock.write_text("", encoding="utf-8")
        os.utime(lock, (when, when))

    assert curation_state("claude_code", str(config)).last_curated_at == "2025-10-15T03:46:40Z"


def test_auto_memory_off_turns_auto_dream_off(tmp_path: pathlib.Path) -> None:
    config = _claude(tmp_path, {"autoMemoryEnabled": False, "autoDreamEnabled": True})

    assert curation_state("claude_code", str(config)).curation == "off"


def test_turn_on_adds_only_the_key_and_keeps_a_backup(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    config = _claude(tmp_path, {"model": "opus", "permissions": {"allow": ["Read"]}})
    settings = config / "settings.json"
    settings.chmod(0o640)

    assert enable_curation("claude_code", str(config)) is True

    assert json.loads(settings.read_text(encoding="utf-8")) == {
        "model": "opus",
        "permissions": {"allow": ["Read"]},
        "autoDreamEnabled": True,
    }
    assert settings.stat().st_mode & 0o777 == 0o640
    backups = list(config_backups_dir().rglob("settings.json.coffer-backup-*"))
    assert len(backups) == 1
    # Already on: nothing is written again.
    assert enable_curation("claude_code", str(config)) is False


def test_codex_has_no_switch_to_turn_on(tmp_path: pathlib.Path) -> None:
    assert enable_curation("codex", str(tmp_path)) is False

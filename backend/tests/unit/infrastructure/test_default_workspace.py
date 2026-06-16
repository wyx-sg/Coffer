"""default_workspace_dir: the Coffer-managed cwd a turn falls back to.

A chat draft or a channel turn that names no working directory must still run
*somewhere*. The product decision (no per-turn cwd UI) is to default to a single
Coffer-managed workspace, creating it on first use, rather than fail the turn.
"""

from __future__ import annotations

from pathlib import Path

from coffer.infrastructure.chat.default_workspace import default_workspace_dir


def test_returns_workspace_under_coffer_home(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HOME", str(tmp_path))
    result = default_workspace_dir()
    assert result == str(tmp_path / ".coffer" / "workspace")


def test_creates_the_directory_when_absent(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HOME", str(tmp_path))
    assert not (tmp_path / ".coffer" / "workspace").exists()
    result = default_workspace_dir()
    assert Path(result).is_dir()


def test_idempotent_when_directory_already_exists(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HOME", str(tmp_path))
    first = default_workspace_dir()
    second = default_workspace_dir()
    assert first == second
    assert Path(second).is_dir()

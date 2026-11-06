"""Shared fixtures for the chat integration tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from coffer.application.chat.turn_orchestrator import clear_active_turns


@pytest.fixture(autouse=True)
def _clear_active_turns_between_tests() -> Iterator[None]:
    """The per-conversation turn registry is process-global; start and end clean."""
    clear_active_turns()
    yield
    clear_active_turns()


@pytest.fixture(autouse=True)
def _daemon_path_is_the_users(monkeypatch: pytest.MonkeyPatch) -> None:
    """A turn sets the agent's PATH only when the daemon's differs from the
    user's login-shell PATH, which depends on the machine running the tests;
    here the two are the same, so a turn's environment is what each test says.
    ``test_agent_path.py`` covers the case where they differ."""
    for module in ("claude_sdk_provider", "codex_provider"):
        monkeypatch.setattr(f"coffer.infrastructure.chat.{module}.user_path_env", dict)

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

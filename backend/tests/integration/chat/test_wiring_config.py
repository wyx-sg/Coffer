"""Tests for chat wiring configuration helpers."""

from __future__ import annotations

import pytest

from coffer.infrastructure.chat.langgraph_agent import DEFAULT_RECURSION_LIMIT
from coffer.surfaces.http.wiring import _agent_recursion_limit


def test_recursion_limit_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COFFER_AGENT_RECURSION_LIMIT", raising=False)
    assert _agent_recursion_limit() == DEFAULT_RECURSION_LIMIT


def test_recursion_limit_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COFFER_AGENT_RECURSION_LIMIT", "40")
    assert _agent_recursion_limit() == 40


def test_recursion_limit_ignores_invalid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COFFER_AGENT_RECURSION_LIMIT", "not-a-number")
    assert _agent_recursion_limit() == DEFAULT_RECURSION_LIMIT


def test_recursion_limit_ignores_non_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COFFER_AGENT_RECURSION_LIMIT", "0")
    assert _agent_recursion_limit() == DEFAULT_RECURSION_LIMIT

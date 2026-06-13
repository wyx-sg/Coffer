"""Unit tests for the opt-in eval-capture emit helpers (ADR-019, slice 2).

The capture half of the eval flywheel records the *shape* of real tool-search
calls (query + the tool names that came back) so the `evals` curate CLI can turn
them into golden cases. Emit must be silent unless explicitly opted in, and must
never raise into a real tool call.
"""

from __future__ import annotations

import json
import logging

import pytest

from coffer.application.eval_capture import (
    CAPTURE_LOGGER_NAME,
    capture_enabled,
    record_tool_search,
)

_ENV = "COFFER_EVAL_CAPTURE"


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_ENV, raising=False)
    assert capture_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "True", "yes", "/tmp/cap.jsonl"])
def test_truthy_values_enable(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(_ENV, value)
    assert capture_enabled() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_falsy_values_stay_disabled(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(_ENV, value)
    assert capture_enabled() is False


def test_record_tool_search_emits_jsonl_when_enabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(_ENV, "1")
    with caplog.at_level(logging.INFO, logger=CAPTURE_LOGGER_NAME):
        record_tool_search("find a file on disk", ["fs__read_file", "fs__write_file"])

    records = [r for r in caplog.records if r.name == CAPTURE_LOGGER_NAME]
    assert len(records) == 1
    payload = json.loads(records[0].getMessage())
    assert payload == {
        "kind": "tool_search",
        "query": "find a file on disk",
        "results": ["fs__read_file", "fs__write_file"],
    }


def test_record_tool_search_silent_when_disabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv(_ENV, raising=False)
    with caplog.at_level(logging.INFO, logger=CAPTURE_LOGGER_NAME):
        record_tool_search("find a file", ["fs__read_file"])
    assert [r for r in caplog.records if r.name == CAPTURE_LOGGER_NAME] == []


def test_record_never_raises_on_bad_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """Capture is best-effort: a non-serialisable argument must be swallowed, not
    bubble up into the real tool call that triggered it."""
    monkeypatch.setenv(_ENV, "1")

    class _Unserialisable:
        pass

    # Should not raise even though the results contain a non-JSON object.
    record_tool_search("q", [_Unserialisable()])  # type: ignore[list-item]

"""The opt-in eval-capture JSONL handler (ADR-019, slice 2).

``install_eval_capture_handler`` binds a file sink to the capture logger only
when ``COFFER_EVAL_CAPTURE`` points somewhere; ``record_tool_search`` then lands
JSONL lines there. These tests touch global logging state, so each restores the
capture logger's handlers and propagate flag afterwards.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from coffer.application.eval_capture import CAPTURE_LOGGER_NAME, record_tool_search
from coffer.infrastructure.logging.eval_capture import install_eval_capture_handler

_ENV = "COFFER_EVAL_CAPTURE"


@pytest.fixture(autouse=True)
def _restore_capture_logger() -> Iterator[None]:
    logger = logging.getLogger(CAPTURE_LOGGER_NAME)
    saved_handlers = logger.handlers[:]
    saved_propagate = logger.propagate
    saved_level = logger.level
    try:
        yield
    finally:
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
        for h in saved_handlers:
            logger.addHandler(h)
        logger.propagate = saved_propagate
        logger.setLevel(saved_level)


def test_handler_writes_jsonl_when_path_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = tmp_path / "capture.jsonl"
    monkeypatch.setenv(_ENV, str(sink))

    install_eval_capture_handler()
    record_tool_search("open the budget sheet", ["sheets__open", "sheets__read"])
    record_tool_search("send a message", ["slack__post"])

    for h in logging.getLogger(CAPTURE_LOGGER_NAME).handlers:
        h.flush()

    lines = sink.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {
        "kind": "tool_search",
        "query": "open the budget sheet",
        "results": ["sheets__open", "sheets__read"],
    }
    assert json.loads(lines[1])["query"] == "send a message"


def test_no_handler_and_no_file_when_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_ENV, raising=False)
    before = len(logging.getLogger(CAPTURE_LOGGER_NAME).handlers)

    install_eval_capture_handler()
    record_tool_search("q", ["a__b"])

    assert len(logging.getLogger(CAPTURE_LOGGER_NAME).handlers) == before
    assert not any(tmp_path.iterdir())


def test_install_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sink = tmp_path / "capture.jsonl"
    monkeypatch.setenv(_ENV, str(sink))

    install_eval_capture_handler()
    install_eval_capture_handler()
    install_eval_capture_handler()

    capture_handlers = [
        h
        for h in logging.getLogger(CAPTURE_LOGGER_NAME).handlers
        if getattr(h, "_coffer_eval_capture", False)
    ]
    assert len(capture_handlers) == 1


def test_flag_value_defaults_to_home_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``COFFER_EVAL_CAPTURE=1`` (a flag, not a path) writes to the default
    ``~/.coffer/eval-capture.jsonl`` — resolved via HOME so tests can redirect."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(_ENV, "1")

    install_eval_capture_handler()
    record_tool_search("q", ["a__b"])
    for h in logging.getLogger(CAPTURE_LOGGER_NAME).handlers:
        h.flush()

    sink = tmp_path / ".coffer" / "eval-capture.jsonl"
    assert sink.exists()
    assert json.loads(sink.read_text(encoding="utf-8").splitlines()[0])["query"] == "q"

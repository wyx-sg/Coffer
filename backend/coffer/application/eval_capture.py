"""Opt-in, dev-only capture of eval-relevant interactions (ADR-019, slice 2).

The capture half of the eval flywheel: when ``COFFER_EVAL_CAPTURE`` is set, the
gateway records the *shape* of real ``coffer__search_tools`` calls — the query
and the tool names that came back — so the ``evals`` curate CLI can turn them
into golden cases. Nothing is captured unless explicitly opted in.

This module stays in the application layer and touches only stdlib ``logging``,
so it does not cross the application -> infrastructure import boundary
(import-linter Contract 2b). The infrastructure side attaches the opt-in JSONL
file handler (``coffer.infrastructure.logging.eval_capture``); here we only
*emit*. Emit is best-effort and never raises: capture must never break the real
tool call that triggered it.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from collections.abc import Sequence

#: Dedicated logger; the infrastructure handler binds a JSONL sink to this name.
CAPTURE_LOGGER_NAME = "coffer.eval_capture"

#: Set to a path (or a truthy flag) to enable capture. Unset/falsy = off.
ENV_VAR = "COFFER_EVAL_CAPTURE"

_FALSY = {"", "0", "false", "no"}

_logger = logging.getLogger(CAPTURE_LOGGER_NAME)


def capture_enabled() -> bool:
    """True when ``COFFER_EVAL_CAPTURE`` is set to anything but a falsy flag."""
    value = os.environ.get(ENV_VAR)
    return value is not None and value.strip().lower() not in _FALSY


def _emit(record: dict[str, object]) -> None:
    if not capture_enabled():
        return
    # Capture is best-effort — a serialisation hiccup must never bubble up into
    # the real tool call that triggered it.
    with contextlib.suppress(Exception):
        _logger.info(json.dumps(record, ensure_ascii=False, sort_keys=True))


def record_tool_search(query: str, results: Sequence[str]) -> None:
    """Capture one ``coffer__search_tools`` call: the query and the ranked tool
    names it returned (in rank order). No-op unless capture is enabled."""
    _emit({"kind": "tool_search", "query": query, "results": list(results)})


__all__ = ["CAPTURE_LOGGER_NAME", "ENV_VAR", "capture_enabled", "record_tool_search"]

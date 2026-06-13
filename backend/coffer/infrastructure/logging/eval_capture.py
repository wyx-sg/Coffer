"""Opt-in JSONL sink for eval capture (ADR-019, slice 2).

The application layer *emits* capture events to the ``coffer.eval_capture``
logger (``coffer.application.eval_capture``). This infrastructure module binds a
file handler to that logger — but only when ``COFFER_EVAL_CAPTURE`` points
somewhere — so capture is off by default and writes nothing in normal operation.

``COFFER_EVAL_CAPTURE`` is read as either a path (write the JSONL there) or a
truthy flag (write to the default ``~/.coffer/eval-capture.jsonl``). The handler
is wired in ``configure_logging`` so the daemon picks it up at startup.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from coffer.application.eval_capture import CAPTURE_LOGGER_NAME, ENV_VAR

_FLAG_TRUE = {"1", "true", "yes"}
_FLAG_FALSE = {"", "0", "false", "no"}

#: Marks our handler so install can stay idempotent across repeated calls.
_MARKER = "_coffer_eval_capture"


def _capture_path() -> Path | None:
    """Resolve the sink path from ``COFFER_EVAL_CAPTURE``, or None when off.

    A truthy flag (``1``/``true``/``yes``) maps to the default
    ``~/.coffer/eval-capture.jsonl``; any other non-falsy value is taken as the
    path itself. HOME is honoured so tests can redirect the default.
    """
    raw = os.environ.get(ENV_VAR)
    if raw is None:
        return None
    value = raw.strip()
    if value.lower() in _FLAG_FALSE:
        return None
    if value.lower() in _FLAG_TRUE:
        return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "eval-capture.jsonl"
    return Path(value).expanduser()


def install_eval_capture_handler() -> None:
    """Bind the JSONL sink to the capture logger when opted in; else no-op.

    Idempotent (safe across daemon boot + tests) and best-effort: if the sink
    directory cannot be created it gives up silently rather than crash startup.
    """
    path = _capture_path()
    if path is None:
        return

    logger = logging.getLogger(CAPTURE_LOGGER_NAME)
    if any(getattr(h, _MARKER, False) for h in logger.handlers):
        return  # already wired

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
    except OSError:
        return  # can't write — give up silently

    handler.setFormatter(logging.Formatter("%(message)s"))  # the JSON line, verbatim
    setattr(handler, _MARKER, True)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # Keep capture out of the main daemon log — this is a separate dev sink.
    logger.propagate = False


__all__ = ["install_eval_capture_handler"]

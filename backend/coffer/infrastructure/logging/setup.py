"""structlog configuration + trace-id contextvar."""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Final

import structlog

_TRACE_ID: ContextVar[str | None] = ContextVar("coffer_trace_id", default=None)
_SENTINEL: Final = "-"


def bind_trace_id(trace_id: str | None) -> None:
    _TRACE_ID.set(trace_id)


def get_trace_id() -> str:
    return _TRACE_ID.get() or _SENTINEL


def _add_trace_id(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    event_dict.setdefault("trace_id", get_trace_id())
    return event_dict


def _log_dir() -> Path:
    """Return the directory for coffer log files.

    Respects COFFER_LOG_DIR env var so tests can redirect output without
    touching the user's ~/.coffer/logs/.
    """
    custom = os.environ.get("COFFER_LOG_DIR")
    if custom:
        return Path(custom)
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "logs"


def _attach_file_handler() -> None:
    """Attach a rotating file handler to the root logger.

    Writes to <COFFER_LOG_DIR>/daemon.log (default ~/.coffer/logs/).
    Max 10 MB per file, 3 backup files kept.
    Silently skips if the directory cannot be created (e.g. read-only FS).
    """
    log_dir = _log_dir()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return  # Can't write — give up silently rather than crash

    log_path = log_dir / "daemon.log"
    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=3,
    )
    # Emit the same format that structlog renders into the %(message)s slot.
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)


def configure_logging(level: str = "INFO") -> None:
    """Idempotent global structlog setup; safe to call multiple times."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=level,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_trace_id,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )
    _attach_file_handler()

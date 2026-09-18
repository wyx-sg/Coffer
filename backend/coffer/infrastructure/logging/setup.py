"""One line format for ``daemon.log``, and why a library cannot change it.

Every record Coffer writes leaves as one JSON object carrying the same fields:
``event`` (the message), ``timestamp``, ``level``, ``logger``, ``trace_id``,
whatever the call site passed as ``extra={...}``, and ``exception`` when there
was a traceback. :mod:`coffer.application.log_reader` reads exactly those keys,
so every row of the Activity page's Daemon tab shows the time, the severity and
the module of the line it came from.

It did not use to. Three things conspired to strip those fields off:

* the root logger's handlers were formatted with ``"%(message)s"``, so the
  timestamp, the level and the logger name — which are on every
  ``LogRecord`` — were formatted *away* on the way to the file, together with
  every ``extra={...}`` field the 100-odd structured call sites pass;
* ``structlog`` was configured to render JSON, but nothing ever logged through
  ``structlog``'s API (there are 119 ``logging.getLogger`` call sites and zero
  ``structlog.get_logger`` ones), so the JSON shape the file was supposed to
  have was never produced by Coffer's own code;
* running a migration called alembic's ``fileConfig``, which *replaces* the
  root logger's handlers — tearing out the rotating file handler and putting
  alembic's ``%(levelname)-5.5s [%(name)s] %(message)s`` console handler in its
  place. The daemon's own log format therefore depended on whether a migration
  had run yet this boot, which is why some lines carried a level and a logger
  and others carried nothing at all.

The formatter is :class:`structlog.stdlib.ProcessorFormatter`: a *stdlib*
formatter, so all 119 ``logging.getLogger`` call sites keep working unchanged,
that runs a structlog processor chain over each record and renders the result
as JSON. :func:`_processors` is that chain, and it is the only place the shape
of a log line is decided. The alembic half of the problem is fixed where it is
caused, in ``infrastructure/persistence/migrations/env.py``.

**One writer per file.** ``daemon.log`` is two things at once: the rotating
file handler's target, and the file a detached daemon's stdout and stderr are
redirected into (:func:`coffer.infrastructure.daemon.spawn.spawn_detached_daemon`
opens it and hands it to the child). A stderr handler therefore wrote every
record into that file a *second* time — the live log holds pairs of identical
lines to prove it, and the Activity page rendered each of Coffer's own log
lines as two rows. So the stderr handler is attached only when stderr is not
already the same file, which is the foreground case (a terminal, or a test)
where it is the only way to see anything at all.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import time
from collections.abc import MutableMapping
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import structlog

from coffer.infrastructure.logging.eval_capture import install_eval_capture_handler
from coffer.infrastructure.logging.files import log_dir

_TRACE_ID: ContextVar[str | None] = ContextVar("coffer_trace_id", default=None)
_SENTINEL: Final = "-"

#: Marks the stderr handler this module owns. ``configure_logging`` runs more
#: than once (daemon boot, tests), and an unmarked handler could not be told
#: apart from pytest's or a library's — so a second call refreshes ours rather
#: than stacking another copy of every line onto the terminal.
_STDERR_MARKER: Final = "_coffer_stderr"


def bind_trace_id(trace_id: str | None) -> None:
    _TRACE_ID.set(trace_id)


def get_trace_id() -> str:
    return _TRACE_ID.get() or _SENTINEL


def _add_trace_id(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    event_dict.setdefault("trace_id", get_trace_id())
    return event_dict


def _add_timestamp(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Stamp ``timestamp`` from the record's own ``created``, not from now.

    ``structlog.processors.TimeStamper`` would read the clock while the line is
    being *formatted*, and a formatter runs once per handler — so the same
    record reached the file and stderr bearing two different times, hundreds of
    microseconds apart. A record has carried its own creation time all along;
    reading that is both cheaper and the honest answer to "when did this
    happen", including for a handler that formats late.

    UTC ISO-8601 with a ``Z``, because that is what the reader compares
    lexically when the Activity page filters by ``since``.
    """
    record: logging.LogRecord | None = event_dict.get("_record")
    created = record.created if record is not None else time.time()
    event_dict.setdefault(
        "timestamp",
        datetime.fromtimestamp(created, UTC).isoformat().replace("+00:00", "Z"),
    )
    return event_dict


def _log_dir() -> Path:
    """Return the directory for coffer log files (see ``logging.files``)."""
    return log_dir()


def _daemon_log_path() -> Path:
    """The file every root handler here is about."""
    return _log_dir() / "daemon.log"


def _processors() -> list[Any]:
    """The fields a log line carries, in the order they appear on it.

    Every entry answers a field that was on the ``LogRecord`` all along and
    never reached the file:

    * ``add_logger_name`` / ``add_log_level`` copy the record's own ``name``
      and ``levelname`` — the module column and the severity badge;
    * ``_add_timestamp`` supplies ``timestamp``, read off the record's own
      creation time;
    * ``ExtraAdder`` copies the ``extra={...}`` dict the call site passed. A
      hundred-odd call sites pass one (``extra={"server": name}``,
      ``extra={"moved": moved}``); under ``"%(message)s"`` every one of them
      was discarded, which made them look like dead weight in the source;
    * ``_add_trace_id`` stamps the request's id, so a failed response's
      ``X-Coffer-Trace`` header can be grepped for in the log — the point of
      :mod:`coffer.surfaces.http.trace`;
    * ``format_exc_info`` renders an ``exc_info=True`` traceback into this
      record's own ``exception`` field. That is what keeps a traceback *inside*
      one JSON line (the newlines are escaped) instead of letting it become a
      run of continuation rows with no time, level or logger of their own.
    """
    return [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        _add_timestamp,
        structlog.stdlib.ExtraAdder(),
        _add_trace_id,
        structlog.processors.format_exc_info,
    ]


def _json_formatter() -> logging.Formatter:
    """The one formatter every handler this module owns is given.

    ``foreign_pre_chain`` is the chain for records that came from the stdlib —
    which is all of them, today. ``remove_processors_meta`` drops the
    bookkeeping keys ``ProcessorFormatter`` adds for its own use, so they do
    not show up as fields on the line.
    """
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_processors(),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )


def _stderr_is(path: Path) -> bool:
    """Whether this process's stderr already *is* ``path``.

    Compared by device+inode, not by name: the redirect arrives as a file
    descriptor the parent opened, and there is no path to read back off one.

    A stderr with no usable descriptor — pytest's capture, a windowless
    build — is not the file, and ``False`` is the safe answer there: it means
    "attach the handler", so output is visible rather than silently dropped.
    """
    try:
        err = os.fstat(sys.stderr.fileno())
        target = path.stat()
    except (OSError, ValueError, AttributeError):
        # OSError/ValueError also cover io.UnsupportedOperation (it subclasses
        # both); AttributeError covers a sys.stderr that is None.
        return False
    return (err.st_dev, err.st_ino) == (target.st_dev, target.st_ino)


def _attach_file_handler(formatter: logging.Formatter | None = None) -> None:
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
    formatter = formatter or _json_formatter()
    # Idempotent attach: configure_logging() may run more than once (daemon
    # boot + tests). Stacking another handler at the same path would duplicate
    # every log line and leak a file descriptor per call, so bail if one is
    # already wired to this daemon.log — after re-pointing it at the current
    # formatter, which is the whole reason it exists.
    root = logging.getLogger()
    target = str(log_path)
    for existing in root.handlers:
        if isinstance(
            existing, logging.handlers.RotatingFileHandler
        ) and existing.baseFilename == os.path.abspath(target):
            existing.setFormatter(formatter)
            return

    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=3,
    )
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)


def _attach_stderr_handler(formatter: logging.Formatter) -> None:
    """Attach the stderr handler — unless stderr is ``daemon.log`` itself.

    See the module docstring: in the daemon's normal, detached life stderr *is*
    the log file, and a second handler writing to it means every record
    appears twice in the file and twice on the page that reads it.

    The stream is bound here, once, and deliberately does not follow a later
    reassignment of ``sys.stderr``. A handler that resolved ``sys.stderr`` at
    emit time instead — the shape ``logging._StderrHandler`` has — sounds more
    correct and is worse: a ``sys.stderr`` swapped out in Python belongs to
    whoever swapped it, and the daemon's log stream is not theirs to collect.
    ``CliRunner`` and ``contextlib.redirect_stderr`` both do exactly that, and
    following them put ``{"event": "HTTP Request: GET …"}`` into the output a
    ``coffer resource list --json`` caller was parsing. A redirect made at the
    file-descriptor level — ``2>&1`` in a shell — is a different thing and
    still applies, because it moves the file behind the stream rather than the
    stream.
    """
    root = logging.getLogger()
    for existing in root.handlers:
        if getattr(existing, _STDERR_MARKER, False):
            existing.setFormatter(formatter)
            return
    if _stderr_is(_daemon_log_path()):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    setattr(handler, _STDERR_MARKER, True)
    root.addHandler(handler)


def configure_logging(level: str = "INFO") -> None:
    """Idempotent global logging setup; safe to call multiple times."""
    formatter = _json_formatter()
    # Set explicitly rather than via basicConfig(level=...): basicConfig does
    # nothing at all once the root logger has handlers, so on the second call
    # the level would be whatever the last library to touch it left behind.
    logging.getLogger().setLevel(level)
    _attach_file_handler(formatter)
    _attach_stderr_handler(formatter)
    # Nothing in Coffer logs through structlog's own API — every call site is
    # ``logging.getLogger``, which is why the formatter above (a stdlib
    # formatter) does all the work. This call is still not decoration:
    # structlog's *default* configuration prints to stdout through its own
    # PrintLogger, so the day a call site does reach for
    # ``structlog.get_logger()``, its records would bypass daemon.log entirely
    # and arrive unformatted. Pointing structlog at the stdlib and ending its
    # chain with ``wrap_for_formatter`` sends such a record through these same
    # handlers and this same formatter, so the file keeps exactly one format.
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            *_processors(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    # Opt-in eval-capture sink (ADR close-the-eval-flywheel): no-op unless
    # COFFER_EVAL_CAPTURE is set.
    install_eval_capture_handler()

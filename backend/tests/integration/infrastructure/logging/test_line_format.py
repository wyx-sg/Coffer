"""Every line Coffer writes into ``daemon.log`` carries the same fields.

The user's report was four columns on the Activity page — time, level, source
module, message — showing a dash for the first three on most rows, including on
alembic's own ``Context impl SQLiteImpl.`` and ``Will assume non-transactional
DDL.``. The fields were never missing from the ``LogRecord``; the root
handlers' ``"%(message)s"`` format threw them away, and a migration's
``fileConfig`` then replaced those handlers altogether.

So these tests assert the invariant rather than the implementation: a record
emitted through ``logging.getLogger(...)`` after ``configure_logging()`` lands
in the file as ONE line that ``application.log_reader`` — the same reader the
Activity page and ``coffer__diagnose`` use — can read a timestamp, a level, a
logger and a message off.
"""

from __future__ import annotations

import io
import json
import logging
import logging.handlers
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog

from coffer.application.log_reader import parse_log_lines
from coffer.infrastructure.logging.setup import (
    _daemon_log_path,
    _stderr_is,
    bind_trace_id,
    configure_logging,
)


@pytest.fixture
def daemon_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A configured logger writing to a throwaway ``daemon.log``.

    The root logger is global state that the rest of the suite also configures,
    so this takes the handlers away for the duration and puts them back — both
    so the assertions below see only this test's lines, and so nothing here
    leaks a handler pointing into a ``tmp_path`` that is about to vanish.
    """
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path))
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    root.handlers = []
    configure_logging()
    try:
        yield tmp_path / "daemon.log"
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = saved_handlers
        root.setLevel(saved_level)


def _records(path: Path) -> list[dict[str, object]]:
    """The file read back the way the Activity page reads it."""
    logging.getLogger().handlers[0].flush()
    return parse_log_lines(path.read_text().splitlines())


@pytest.mark.acceptance(
    spec="daemon", scenario="every line the daemon writes carries the same fields"
)
def test_a_stdlib_record_lands_with_all_four_fields(daemon_log: Path) -> None:
    """The invariant. No call site changed to get this — the 119 of them go
    through ``logging.getLogger``, and that is the whole point."""
    bind_trace_id("trace-abc")
    try:
        logging.getLogger("coffer.application.mcp.supervisor").warning("mcp.upstream.spawn_failed")
    finally:
        bind_trace_id(None)

    lines = daemon_log.read_text().splitlines()
    assert len(lines) == 1, f"expected one line per record, got {lines}"
    record = json.loads(lines[0])
    assert record["event"] == "mcp.upstream.spawn_failed"
    assert record["level"] == "warning"
    assert record["logger"] == "coffer.application.mcp.supervisor"
    assert record["timestamp"].endswith("Z")  # UTC, and lexically sortable
    assert record["trace_id"] == "trace-abc"


def test_the_reader_lifts_those_fields_back_off_the_line(daemon_log: Path) -> None:
    """Producing the fields is only half of it: the four columns are filled by
    ``log_reader``, so the shape written has to be the shape it reads."""
    logging.getLogger("coffer.application.sync.worker").error("sync.converge_failed")

    records = _records(daemon_log)
    assert len(records) == 1
    assert "raw" not in records[0], "the line fell through to the raw fallback"
    assert records[0]["level"] == "error"
    assert records[0]["logger"] == "coffer.application.sync.worker"
    assert records[0]["event"] == "sync.converge_failed"
    assert records[0]["timestamp"]


@pytest.mark.acceptance(
    spec="daemon", scenario="every line the daemon writes carries the same fields"
)
def test_alembics_own_info_lines_arrive_through_coffers_formatter(
    daemon_log: Path,
) -> None:
    """The two lines in the user's screenshot.

    Alembic logs them on an ordinary stdlib logger. They used to reach the file
    through alembic's own console handler — level and logger, never a time —
    or, before a migration had run, with nothing at all. Nothing configures
    them now; they simply propagate to the root logger the daemon owns.
    """
    logger = logging.getLogger("alembic.runtime.migration")
    logger.info("Context impl SQLiteImpl.")
    logger.info("Will assume non-transactional DDL.")

    records = _records(daemon_log)
    assert [r["event"] for r in records] == [
        "Context impl SQLiteImpl.",
        "Will assume non-transactional DDL.",
    ]
    for record in records:
        assert record["level"] == "info"
        assert record["logger"] == "alembic.runtime.migration"
        assert record["timestamp"], "the row would render a dash in the time column"


@pytest.mark.acceptance(
    spec="daemon", scenario="every line the daemon writes carries the same fields"
)
def test_a_traceback_stays_inside_the_record_that_raised(daemon_log: Path) -> None:
    """``exc_info=True`` is used at many call sites. The traceback has to end
    up in the one record — JSON escapes its newlines — rather than becoming a
    run of rows with no time, level or logger of their own."""
    try:
        raise ValueError("the upstream said no")
    except ValueError:
        logging.getLogger("coffer.application.channel.inbound").exception("channel.inbound_failed")

    lines = daemon_log.read_text().splitlines()
    assert len(lines) == 1, f"the traceback became extra lines: {lines}"
    record = json.loads(lines[0])
    assert record["level"] == "error"
    assert record["logger"] == "coffer.application.channel.inbound"
    assert "Traceback (most recent call last):" in record["exception"]
    assert "ValueError: the upstream said no" in record["exception"]
    # And the reader keeps it one record, not one plus a heap of continuations.
    records = _records(daemon_log)
    assert len(records) == 1
    assert "continuation" not in records[0]


def test_the_extra_a_call_site_passes_becomes_fields(daemon_log: Path) -> None:
    """A hundred-odd call sites pass ``extra={...}``; under ``"%(message)s"``
    every one of those dicts was formatted away, so the structured data they
    went to the trouble of gathering reached nobody."""
    logging.getLogger("coffer.application.binary_deploy").info(
        "binary_deploy.completed", extra={"binaries": ["coffer", "coffer-daemon"], "count": 2}
    )

    record = json.loads(daemon_log.read_text().splitlines()[0])
    assert record["binaries"] == ["coffer", "coffer-daemon"]
    assert record["count"] == 2
    # The bookkeeping keys ProcessorFormatter adds for its own use must not
    # leak onto the line.
    assert "_record" not in record
    assert "_from_structlog" not in record


def test_both_handlers_render_a_record_identically(daemon_log: Path) -> None:
    """The file and stderr are two handlers formatting the same record, so a
    timestamp read from the clock at format time gave the two sinks different
    times for one event. It comes off the record instead."""
    root = logging.getLogger()
    # pytest attaches its own capture handlers to the root logger around every
    # test, so pick out the ones this module installed rather than counting.
    formatters = [
        h.formatter
        for h in root.handlers
        if isinstance(h.formatter, structlog.stdlib.ProcessorFormatter)
    ]
    assert len(formatters) == 2, "expected the file handler and the stderr handler"
    record = logging.makeLogRecord(
        {"levelno": logging.INFO, "levelname": "INFO", "name": "coffer.test", "msg": "once"}
    )
    rendered = {formatter.format(record) for formatter in formatters if formatter}
    assert len(rendered) == 1, f"the two handlers disagree about one record: {rendered}"


@pytest.mark.acceptance(
    spec="daemon", scenario="every line the daemon writes carries the same fields"
)
def test_no_stderr_handler_when_stderr_is_the_log_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``spawn_detached_daemon`` gives the daemon ``daemon.log`` as its stderr,
    so a stderr handler would write every record into the file a second time —
    which is exactly what the live log shows, pairs of identical lines, and
    what the Activity page rendered as duplicate rows."""
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path))
    log_path = tmp_path / "daemon.log"
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    root.handlers = []
    with log_path.open("ab") as as_stderr:
        monkeypatch.setattr("sys.stderr", as_stderr)
        try:
            assert _stderr_is(_daemon_log_path()), "fixture did not redirect stderr"
            configure_logging()
            logging.getLogger("coffer.test").warning("once")
            handlers = root.handlers[:]
        finally:
            for handler in root.handlers:
                handler.close()
            root.handlers = saved_handlers
            root.setLevel(saved_level)

    assert [type(h) for h in handlers] == [logging.handlers.RotatingFileHandler]
    assert log_path.read_text().count('"event": "once"') == 1


def test_a_record_does_not_follow_a_reassigned_sys_stderr(daemon_log: Path) -> None:
    """The daemon's log stream must not be collected by whoever replaced
    ``sys.stderr``.

    The handler is bound to the stream once, at attach time, and a later
    ``sys.stderr = ...`` — Click's ``CliRunner``, ``redirect_stderr`` — does
    not move it. A handler that resolved ``sys.stderr`` at emit time instead
    sounds more correct and is worse: it put the daemon's `HTTP Request: GET …`
    records into the output a `coffer resource list --json` caller was parsing,
    which broke 71 CLI tests in one go and would break a script the same way.

    (A redirect made at the file-descriptor level, ``2>&1``, still applies and
    should: it moves the file behind the stream, not the stream.)
    """
    hijacked = io.StringIO()
    real_stderr = sys.stderr
    sys.stderr = hijacked
    try:
        logging.getLogger("httpx").info('HTTP Request: GET /api/v1/resources "200 OK"')
    finally:
        sys.stderr = real_stderr

    assert hijacked.getvalue() == "", (
        f"the record followed sys.stderr into a caller's own output: {hijacked.getvalue()!r}"
    )
    # It still reached the log, which is where it belongs.
    assert "HTTP Request" in daemon_log.read_text()

"""Verify that configure_logging() attaches a rotating file handler.

Uses COFFER_LOG_DIR to redirect log output to a tmp_path so this test
never writes to the user's ~/.coffer/logs/.

NOTE: pytest's log-capture plugin intercepts root-logger calls during test
execution, which means records written through logging.getLogger() may not
reach our RotatingFileHandler.  We work around this by emitting a log record
directly into the handler (bypassing pytest capture) to verify the handler
itself writes to disk correctly.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

import pytest

from coffer.infrastructure.logging.setup import _attach_file_handler, configure_logging


def test_file_handler_attaches_on_configure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """configure_logging() must add a RotatingFileHandler to the root logger."""
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path))

    root = logging.getLogger()

    # Remove any previously-attached file handlers so this test is isolated.
    for h in list(root.handlers):
        if isinstance(h, logging.handlers.RotatingFileHandler):
            root.removeHandler(h)
            h.close()

    configure_logging()

    file_handlers = [
        h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert file_handlers, "configure_logging() did not attach a RotatingFileHandler"

    handler = file_handlers[0]
    assert handler.baseFilename == str(tmp_path / "daemon.log"), (
        f"Handler points at {handler.baseFilename!r}, expected {tmp_path / 'daemon.log'}"
    )
    assert handler.maxBytes == 10 * 1024 * 1024, "Expected 10 MB max file size"
    assert handler.backupCount == 3, "Expected 3 backup files"


def test_configure_logging_is_idempotent_for_file_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calling configure_logging() repeatedly must not stack duplicate file
    handlers on the root logger.

    The daemon (and tests) may call configure_logging() more than once; each
    call previously appended another RotatingFileHandler, so every log line
    was written N times and N file descriptors leaked. The attach must be
    idempotent: exactly one RotatingFileHandler regardless of call count.
    """
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path))

    root = logging.getLogger()
    # Start from a clean slate so prior tests don't skew the count.
    for h in list(root.handlers):
        if isinstance(h, logging.handlers.RotatingFileHandler):
            root.removeHandler(h)
            h.close()

    configure_logging()
    configure_logging()
    configure_logging()

    file_handlers = [
        h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert len(file_handlers) == 1, (
        f"configure_logging() stacked {len(file_handlers)} file handlers; expected 1"
    )


def test_file_handler_writes_to_coffer_log_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The RotatingFileHandler must write log records to daemon.log.

    We bypass pytest's log-capture plugin by emitting a LogRecord directly
    into the handler rather than going through logging.getLogger(), which
    pytest intercepts.
    """
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path))

    # Attach a fresh handler pointing at tmp_path.
    _attach_file_handler()

    root = logging.getLogger()
    file_handlers = [
        h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert file_handlers, "_attach_file_handler() did not add a RotatingFileHandler"
    handler = file_handlers[-1]  # The most recently attached one.

    # Emit a record directly into the handler (bypasses pytest capture).
    record = logging.makeLogRecord(
        {
            "levelno": logging.INFO,
            "levelname": "INFO",
            "name": "coffer.test",
            "msg": "hello world from test",
            "args": (),
        }
    )
    handler.emit(record)
    handler.flush()

    log_file = tmp_path / "daemon.log"
    assert log_file.exists(), f"daemon.log not written under {tmp_path}"
    contents = log_file.read_text()
    assert "hello world from test" in contents, (
        f"Expected 'hello world from test' in daemon.log; got:\n{contents}"
    )


@pytest.mark.acceptance(
    spec="daemon", scenario="output written to stderr after a rotation lands in the current log"
)
def test_rotation_carries_the_process_stderr_to_the_new_file(tmp_path: Path) -> None:
    """The detached daemon's fd 2 *is* daemon.log; rotation must not strand it
    in daemon.log.1, where nothing reads it and it is deleted after three
    rollovers (spec daemon "Write one bounded daemon log in one format")."""
    import subprocess
    import sys

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    script = (
        "import logging, sys\n"
        "from coffer.infrastructure.logging import setup\n"
        "h = setup._FdFollowingRotatingHandler("
        f"{str(log_dir / 'daemon.log')!r}, maxBytes=200, backupCount=2)\n"
        "logging.getLogger().addHandler(h)\n"
        "logging.getLogger().setLevel('INFO')\n"
        "for i in range(10):\n"
        "    logging.info('x' * 60)\n"
        "sys.stderr.write('RAW-AFTER-ROTATION\\n'); sys.stderr.flush()\n"
    )
    with open(log_dir / "daemon.log", "ab") as f:
        subprocess.run([sys.executable, "-c", script], stdout=f, stderr=f, check=True)
    assert "RAW-AFTER-ROTATION" in (log_dir / "daemon.log").read_text()
    assert not any("RAW-AFTER-ROTATION" in p.read_text() for p in log_dir.glob("daemon.log.*"))

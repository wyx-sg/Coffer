"""Run a command-line tool's help, and nothing else.

``HelpRunner`` is the only way Coffer runs a tool to read its interface, and
it is built so a tool cannot be made to do anything but print its help:

- argv is ``[path, *subcommand names, flag]`` with ``flag`` one of the literals
  ``--help`` / ``-h`` (or ``[path, "help", *names]``): the caller cannot pass
  any other argument, and each subcommand name must look like a name — never a
  flag, a path or a shell word. There is no shell.
- stdin is closed; stdout and stderr are one pipe, read up to a cap (a tool
  that never stops printing cannot fill the daemon's memory) and the process
  is killed at its timeout, with its process group.
- The environment is built from nothing: ``PATH``, a throw-away ``HOME`` and
  working directory (so a tool that writes a cache writes it there, not in the
  person's home), ``LANG``, and three display settings (no colour, a dumb
  terminal, a fixed width) so help is plain and wraps predictably. Nothing
  Coffer or the person's shell holds — tokens, API keys, ``COFFER_*``,
  ``SSH_AUTH_SOCK`` — is inherited.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import signal
import subprocess
import tempfile
import threading
from collections.abc import Callable, Sequence

from coffer.application.skill.cli_discovery import HelpFlag, HelpOutput

_log = logging.getLogger(__name__)

HELP_TIMEOUT_SECONDS = 5.0
#: The most of one help text that is read.
MAX_HELP_OUTPUT = 256 * 1024
_FLAGS = ("--help", "-h", "help")
_SUBCOMMAND = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")


class HelpRefused(ValueError):  # noqa: N818
    """The arguments are not a help request; nothing was run."""


def help_argv(path: str, subcommands: Sequence[str], flag: str) -> list[str]:
    """The argv for a help request, or :class:`HelpRefused`."""
    if flag not in _FLAGS:
        raise HelpRefused(f"{flag!r} is not a help flag")
    if not os.path.isabs(path):
        raise HelpRefused("the tool must be given by absolute path")
    if not all(_SUBCOMMAND.match(name) for name in subcommands):
        raise HelpRefused("a subcommand name is not a plain name")
    if flag == "help":
        return [path, "help", *subcommands]
    return [path, *subcommands, flag]


class HelpRunner:
    def __init__(
        self,
        *,
        user_path: Callable[[], str],
        timeout: float = HELP_TIMEOUT_SECONDS,
        max_output: int = MAX_HELP_OUTPUT,
    ) -> None:
        self._user_path = user_path
        self._timeout = timeout
        self._max = max_output

    def run(self, path: str, subcommands: Sequence[str], flag: HelpFlag) -> HelpOutput:
        argv = help_argv(path, subcommands, flag)
        with tempfile.TemporaryDirectory(prefix="coffer-help-") as scratch:
            return self._run(argv, scratch)

    def _env(self, scratch: str) -> dict[str, str]:
        return {
            "PATH": self._user_path(),
            "HOME": scratch,
            "LANG": "en_US.UTF-8",
            "NO_COLOR": "1",
            "TERM": "dumb",
            "COLUMNS": "120",
        }

    def _run(self, argv: list[str], scratch: str) -> HelpOutput:
        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=self._env(scratch),
                cwd=scratch,
                start_new_session=True,
            )
        except OSError as exc:
            _log.debug("skill.help_runner.start_failed program=%s", argv[0], exc_info=True)
            return HelpOutput("", error=f"could not start: {exc.strerror or exc}")
        timed_out = threading.Event()

        def stop() -> None:
            timed_out.set()
            _kill(proc)

        timer = threading.Timer(self._timeout, stop)
        timer.start()
        try:
            assert proc.stdout is not None
            raw = proc.stdout.read(self._max + 1)
        except (OSError, ValueError):
            raw = b""
        finally:
            timer.cancel()
            _kill(proc)
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                proc.wait(timeout=2)
            if proc.stdout is not None:
                proc.stdout.close()
        return HelpOutput(
            raw[: self._max].decode("utf-8", errors="replace"),
            truncated=len(raw) > self._max,
            timed_out=timed_out.is_set(),
        )


def _kill(proc: subprocess.Popen[bytes]) -> None:
    with contextlib.suppress(OSError, AttributeError):
        os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(OSError):
        proc.kill()


__all__ = [
    "HELP_TIMEOUT_SECONDS",
    "MAX_HELP_OUTPUT",
    "HelpRefused",
    "HelpRunner",
    "help_argv",
]

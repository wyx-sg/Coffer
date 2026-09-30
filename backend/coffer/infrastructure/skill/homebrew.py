"""Install or upgrade a command through Homebrew — the only installer Coffer
offers (spec skill-manager "Install a required command only through Homebrew
and only when asked").

Argv with no shell and never ``sudo``, as the daemon's user, with
``HOMEBREW_NO_AUTO_UPDATE=1`` and ``NONINTERACTIVE=1`` and ``stdin`` closed so
nothing can wait on a prompt. Output is stdout and stderr merged and handed on
line by line while it runs; a run past the ceiling is killed.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import threading
from collections.abc import Callable, Sequence

from coffer.infrastructure.platform.process import executable_name

INSTALL_TIMEOUT_SECONDS = 15 * 60.0


class HomebrewInstaller:
    """``InstallerPort`` over the machine's Homebrew."""

    def __init__(
        self, *, user_path: Callable[[], str], timeout: float = INSTALL_TIMEOUT_SECONDS
    ) -> None:
        self._user_path = user_path
        self._timeout = timeout

    def locate(self) -> str | None:
        """``brew`` on the agent's ``PATH``, or ``None``."""
        return shutil.which(executable_name("brew"), path=self._user_path())

    def run(self, argv: Sequence[str], on_line: Callable[[str], None]) -> int:
        """Run ``argv`` to its end and return its exit code; ``on_line`` gets
        every output line as it arrives. Blocking — call it off the loop."""
        env = {
            **os.environ,
            "PATH": self._user_path(),
            "HOMEBREW_NO_AUTO_UPDATE": "1",
            "NONINTERACTIVE": "1",
        }
        proc = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
            env=env,
            # Its own process group, so the ceiling stops the downloads and
            # builds brew starts too, not only brew itself.
            start_new_session=True,
        )
        timed_out = threading.Event()

        def _kill() -> None:
            timed_out.set()
            killpg = getattr(os, "killpg", None)
            if killpg is not None:
                with contextlib.suppress(OSError):
                    killpg(proc.pid, signal.SIGKILL)
            with contextlib.suppress(OSError):
                proc.kill()

        timer = threading.Timer(self._timeout, _kill)
        timer.daemon = True
        timer.start()
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                on_line(line.rstrip("\r\n"))
            code = proc.wait()
        finally:
            timer.cancel()
        if timed_out.is_set():
            on_line(f"coffer: stopped after {int(self._timeout // 60)} minutes")
        return code


__all__ = ["INSTALL_TIMEOUT_SECONDS", "HomebrewInstaller"]

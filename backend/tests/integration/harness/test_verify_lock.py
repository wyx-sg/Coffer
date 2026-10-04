"""Tests for scripts/verify_lock.py — one integration run per machine.

A second run waits for the first instead of competing with it. The lock is
released when its holder exits, the command's exit code (and a signal death,
as 128+N) comes back, and ``COFFER_VERIFY_LOCK=off`` skips the lock.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "verify_lock.py"


def _env(cache: Path, **extra: str) -> dict[str, str]:
    env = {**os.environ, "XDG_CACHE_HOME": str(cache)}
    env.pop("COFFER_VERIFY_LOCK", None)
    env.update(extra)
    return env


def _wait_for_file(path: Path, timeout: float = 30.0) -> None:
    """Block until the lock holder's child says it is running (so it holds the lock)."""
    deadline = time.monotonic() + timeout
    while not path.exists():
        assert time.monotonic() < deadline, f"{path.name} never appeared"
        time.sleep(0.02)


def _run(cache: Path, *command: str, **extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--", *command],
        env=_env(cache, **extra),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_the_command_runs_and_its_exit_code_comes_back(tmp_path: Path) -> None:
    done = _run(tmp_path, sys.executable, "-c", "import sys; print('ran'); sys.exit(3)")
    assert done.returncode == 3
    assert "ran" in done.stdout
    assert (tmp_path / "coffer" / "verify-integration.lock").exists()


def test_a_second_run_waits_for_the_first(tmp_path: Path) -> None:
    marker = tmp_path / "first-done"
    holding = tmp_path / "first-holding"
    first = subprocess.Popen(
        [
            sys.executable,
            str(_SCRIPT),
            "--",
            sys.executable,
            "-c",
            f"import time, pathlib; pathlib.Path({str(holding)!r}).write_text('x'); "
            f"time.sleep(2); pathlib.Path({str(marker)!r}).write_text('x')",
        ],
        env=_env(tmp_path),
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_file(holding)  # the first run holds the lock
        second = _run(
            tmp_path,
            sys.executable,
            "-c",
            f"import pathlib, sys; sys.exit(0 if pathlib.Path({str(marker)!r}).exists() else 1)",
        )
        assert second.returncode == 0, "the second run started before the first finished"
        assert "waiting for pid" in second.stderr
    finally:
        first.wait(timeout=30)
    assert first.returncode == 0


def test_a_holder_that_dies_releases_the_lock(tmp_path: Path) -> None:
    holding = tmp_path / "holder-holding"
    holder = subprocess.Popen(
        [
            sys.executable,
            str(_SCRIPT),
            "--",
            sys.executable,
            "-c",
            f"import time, pathlib; pathlib.Path({str(holding)!r}).write_text('x'); time.sleep(5)",
        ],
        env=_env(tmp_path),
    )
    _wait_for_file(holding)
    holder.kill()  # the wrapper itself dies without cleaning up
    holder.wait(timeout=10)
    started = time.monotonic()
    done = _run(tmp_path, sys.executable, "-c", "pass")
    assert done.returncode == 0
    # The orphaned 5 s child no longer holds anything: the lock was the wrapper's.
    assert time.monotonic() - started < 4


def test_a_signal_death_is_reported_as_128_plus_n(tmp_path: Path) -> None:
    done = _run(
        tmp_path, sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"
    )
    assert done.returncode == 128 + 15


def test_the_lock_can_be_switched_off(tmp_path: Path) -> None:
    done = _run(tmp_path, sys.executable, "-c", "pass", COFFER_VERIFY_LOCK="off")
    assert done.returncode == 0
    assert not (tmp_path / "coffer").exists()


def test_a_command_is_required(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(_SCRIPT)], env=_env(tmp_path), capture_output=True, text=True
    )
    assert done.returncode == 2

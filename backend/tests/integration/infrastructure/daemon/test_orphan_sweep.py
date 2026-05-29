"""Integration tests for orphan_sweep module (T-051)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from coffer.infrastructure.daemon.orphan_sweep import (
    _pid_dir,
    forget_spawn,
    record_spawn,
    sweep_orphans,
)


def test_record_and_forget(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
    proc = subprocess.Popen(cmd)
    try:
        path = record_spawn("test_server", proc.pid, cmd)
        assert path.exists()
        payload = json.loads(path.read_text())
        assert payload["pid"] == proc.pid
        forget_spawn(path)
        assert not path.exists()
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_sweep_no_dir_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert sweep_orphans() == 0


def test_sweep_kills_live_orphan(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    # Spawn a real long-sleeping child
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        record_spawn(
            "test_server",
            proc.pid,
            [sys.executable, "-c", "import time; time.sleep(60)"],
        )
        killed = sweep_orphans()
        assert killed == 1
        # The process should be dead now
        time.sleep(0.5)
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)


def test_sweep_skips_dead_pid(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    # Spawn + reap immediately
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=5)
    # PID is now dead; record a file pointing at it
    record_spawn("test_server", proc.pid, [sys.executable, "-c", "pass"])
    killed = sweep_orphans()
    # Dead PIDs aren't "killed" but their files are reaped
    assert killed == 0
    assert list(_pid_dir().glob("*.json")) == []


def test_sweep_skips_pid_recycled_with_different_cmdline(tmp_path, monkeypatch):
    """If the PID happens to be live but the command differs (recycled by OS),
    don't kill it — we'd be killing a stranger."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Use this Python process's own PID as the "recycled" one; we obviously
    # don't want sweep_orphans to kill the test runner.
    own_pid = os.getpid()
    record_spawn(
        "test_server",
        own_pid,
        ["definitely_not_our_actual_cmdline_zzz"],
    )
    killed = sweep_orphans()
    assert killed == 0
    # File is reaped because cmdline didn't match
    assert list(_pid_dir().glob("*.json")) == []

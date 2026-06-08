"""Integration tests for orphan_sweep module (T-051)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import psutil

from coffer.infrastructure.daemon.orphan_sweep import (
    _pid_dir,
    forget_spawn,
    reap_pidfile,
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


def test_reap_pidfile_kills_process_and_descendants(tmp_path, monkeypatch):
    """reap_pidfile must kill the recorded process AND its descendants — the
    real leak is a `uv tool uvx` wrapper whose python grandchild outlives a
    naive single-PID kill."""
    monkeypatch.setenv("HOME", str(tmp_path))
    code = (
        "import subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "time.sleep(60)"
    )
    parent = subprocess.Popen([sys.executable, "-c", code])
    try:
        # Wait for the grandchild to appear.
        kids: list = []
        deadline = time.time() + 5
        while time.time() < deadline:
            kids = psutil.Process(parent.pid).children(recursive=True)
            if kids:
                break
            time.sleep(0.05)
        assert kids, "grandchild process never spawned"
        kid_pids = [k.pid for k in kids]

        # Record the *actual* cmdline psutil reports, exactly as production
        # does (subprocess.py records psutil.Process(pid).cmdline()); the venv
        # python3 wrapper execs the framework interpreter so the constructed
        # argv would never match the recycle-guard.
        actual_cmd = psutil.Process(parent.pid).cmdline()
        path = record_spawn("test_server", parent.pid, actual_cmd)
        assert reap_pidfile(path) is True
        assert not path.exists()

        time.sleep(0.5)
        assert parent.poll() is not None
        for kp in kid_pids:
            assert not psutil.pid_exists(kp)
    finally:
        if parent.poll() is None:
            parent.terminate()
            parent.wait(timeout=5)


def test_reap_pidfile_dead_pid_returns_false_and_removes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=5)
    path = record_spawn("test_server", proc.pid, [sys.executable, "-c", "pass"])
    assert reap_pidfile(path) is False
    assert not path.exists()


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

"""The daemon boots to ready inside its startup budget.

A real ``coffer.infrastructure.daemon.entry`` process on a fake ``HOME`` with
an empty vault, from spawn to the first ``/api/v1/daemon/status`` that answers
``ready`` (what the desktop shell and the CLI's detect-or-spawn wait for).
uvicorn serves only after the lifespan's startup half returns, so that answer
is the whole boot: imports, migrations on a fresh database, the vault's first
commit, every worker the lifespan starts.

The budget is **CPU time**, the daemon's own plus that of the children it
reaped (its git calls). Wall-clock time to ready measured 2.4-22 s on the same
Apple-silicon laptop on 2026-10-01, depending on what else ran: process
launches there slow to seconds under load. CPU time measured 2.4-2.7 s across
those same runs, so the ceiling is about three times that: it fails when boot
starts doing work it should not (a scan of something that grows, a migration
that rewrites everything), not when the machine is busy. A wall-clock limit
stays only as a hang guard, for boot waiting on something (a network call, a
lock). Cheap enough for ``make verify``; also marked ``benchmark`` so ``make
verify-benchmark`` runs every budget.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil
import pytest

import coffer

#: CPU seconds the daemon (and the children it reaped) may spend from spawn
#: to ready (see the module docstring for the measurement).
CPU_CEILING_S = 8.0
#: Wall-clock seconds from spawn to ready: only a hang guard.
WALL_CEILING_S = 60.0

_SOURCE = str(Path(coffer.__file__).resolve().parent.parent)

pytestmark = pytest.mark.benchmark


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _ready(home: Path) -> bool:
    info_path = home / ".coffer" / "daemon.json"
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
        r = httpx.get(
            f"http://127.0.0.1:{info['port']}/api/v1/daemon/status",
            headers={"X-Coffer-Token": info["token"]},
            timeout=2,
            trust_env=False,
        )
    except (OSError, ValueError, KeyError, httpx.HTTPError):
        return False
    return r.status_code == 200 and r.json().get("status") == "ready"


def _cpu_seconds(proc: psutil.Process) -> float:
    """The daemon's CPU time so far, with that of the children it has reaped
    (git, migrations' helpers)."""
    t = proc.cpu_times()
    return float(t.user + t.system + t.children_user + t.children_system)


def test_the_daemon_boots_to_ready_inside_its_ceiling(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".coffer").mkdir(parents=True)
    port = _free_port()
    env = {
        **os.environ,
        "HOME": str(home),
        "COFFER_DB_URL": f"sqlite+aiosqlite:///{home / 'runs.db'}",
        "COFFER_KNOWLEDGE_ROOT": str(tmp_path / "knowledge"),
        "COFFER_LOG_DIR": str(home / "logs"),
        "COFFER_PORT_RANGE_START": str(port),
        "COFFER_PORT_RANGE_END": str(port + 9),
        "PYTHONPATH": _SOURCE,
    }
    # A file, not a pipe: nobody reads stderr while the daemon boots, and a
    # full pipe would stall it.
    errors = tmp_path / "daemon.stderr"
    started = time.monotonic()
    with errors.open("wb") as sink:
        proc = subprocess.Popen(
            [sys.executable, "-m", "coffer.infrastructure.daemon.entry"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=sink,
        )
    watched = psutil.Process(proc.pid)
    try:
        deadline = started + WALL_CEILING_S
        while not _ready(home):
            assert proc.poll() is None, errors.read_text(errors="replace")
            assert time.monotonic() < deadline, (
                f"the daemon was not ready after {WALL_CEILING_S:.0f} s: it is waiting on "
                "something (a network call, a lock), not just slow"
            )
            time.sleep(0.05)
        cpu = _cpu_seconds(watched)
        elapsed = time.monotonic() - started
        print(
            f"\ndaemon spawn to ready: {elapsed:.2f} s wall, {cpu:.2f} s CPU "
            f"(ceilings {WALL_CEILING_S:.0f} s, {CPU_CEILING_S:.0f} s)"
        )
        assert cpu < CPU_CEILING_S, (
            f"the daemon spent {cpu:.1f} s of CPU becoming ready; the ceiling is "
            f"{CPU_CEILING_S:.0f} s"
        )
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

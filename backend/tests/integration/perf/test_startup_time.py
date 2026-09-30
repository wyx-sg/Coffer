"""The daemon boots to ready inside its startup budget.

A real ``coffer.infrastructure.daemon.entry`` process on a fake ``HOME`` with
an empty vault: the clock runs from spawning the process to the first
``/api/v1/daemon/status`` that answers ``ready``, which is what the desktop
shell and the CLI's detect-or-spawn wait for. uvicorn serves only after the
lifespan's startup half returns, so that answer is the whole boot: imports,
migrations on a fresh database, the vault's first commit, every worker the
lifespan starts.

Measured 2026-10-01 on an Apple-silicon laptop shared with other work:
2.4-4.5 s from spawn to ready at a load average of 6-15, 4.7-6.6 s at 20-27.
The ceiling is 2-3 times the loaded end of that, so it fails when boot starts
doing work it should not (a network call, a scan of something that grows),
not when the machine is busy. Cheap enough for ``make verify``; also marked
``benchmark`` so ``make verify-benchmark`` runs every budget.
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
import pytest

import coffer

#: Spawn to ready, in seconds (see the module docstring for the measurement).
STARTUP_CEILING_S = 15.0

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


def test_the_daemon_boots_to_ready_inside_its_ceiling(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".coffer").mkdir(parents=True)
    port = _free_port()
    env = {
        **os.environ,
        "HOME": str(home),
        "COFFER_DB_URL": f"sqlite+aiosqlite:///{home / 'coffer.db'}",
        "COFFER_KNOWLEDGE_ROOT": str(tmp_path / "knowledge"),
        "COFFER_LOG_DIR": str(home / "logs"),
        "COFFER_PORT_RANGE_START": str(port),
        "COFFER_PORT_RANGE_END": str(port + 9),
        "PYTHONPATH": _SOURCE,
    }
    started = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, "-m", "coffer.infrastructure.daemon.entry"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        # Poll well past the ceiling, so a slow boot reports its real time
        # rather than a bare "never became ready".
        deadline = started + STARTUP_CEILING_S * 4
        while not _ready(home):
            assert proc.poll() is None, proc.stderr.read().decode() if proc.stderr else ""
            assert time.monotonic() < deadline, "the daemon never became ready"
            time.sleep(0.05)
        elapsed = time.monotonic() - started
        print(f"\ndaemon spawn to ready: {elapsed:.2f} s (ceiling {STARTUP_CEILING_S:.0f} s)")
        assert elapsed < STARTUP_CEILING_S, (
            f"the daemon took {elapsed:.1f} s to become ready; the ceiling is "
            f"{STARTUP_CEILING_S:.0f} s"
        )
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

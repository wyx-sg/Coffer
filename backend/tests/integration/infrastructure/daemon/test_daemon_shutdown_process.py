"""Stopping a real daemon process leaves no discovery file behind (spec daemon
"Shut down through one graceful exit path" scenario "stopping the daemon leaves no discovery file").

The unit-sized checks of ``bootstrap.release`` cannot show that the whole path
— the shutdown route, uvicorn's graceful stop, the entry's ``finally`` — ends
with the file gone and the process exited, so this one starts the real thing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


def _wait(predicate, timeout: float) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.2)
    return False


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
@pytest.mark.acceptance(spec="daemon", scenario="stopping the daemon leaves no discovery file")
def test_a_shutdown_request_ends_the_process_and_removes_daemon_json(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "COFFER_PORT_RANGE_START": "59600",
        "COFFER_PORT_RANGE_END": "59609",
        "COFFER_LOG_DIR": str(tmp_path / "logs"),
    }
    log = (tmp_path / "daemon.out").open("wb")
    proc = subprocess.Popen(
        [sys.executable, "-m", "coffer.infrastructure.daemon.entry"],
        env=env,
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
    )
    daemon_json = home / ".coffer" / "daemon.json"
    try:

        def _serving() -> bool:
            if proc.poll() is not None or not daemon_json.exists():
                return False
            try:
                info = json.loads(daemon_json.read_text())
                return (
                    httpx.get(
                        f"http://127.0.0.1:{info['port']}/api/v1/daemon/status", timeout=5
                    ).status_code
                    == 200
                )
            except (OSError, ValueError, httpx.HTTPError):
                return False

        assert _wait(_serving, 90), (tmp_path / "daemon.out").read_text()
        info = json.loads(daemon_json.read_text())
        # An unauthenticated shutdown is refused and changes nothing.
        refused = httpx.post(f"http://127.0.0.1:{info['port']}/api/v1/daemon/shutdown", timeout=5)
        assert refused.status_code in (401, 403)
        assert proc.poll() is None and daemon_json.exists()

        done = httpx.post(
            f"http://127.0.0.1:{info['port']}/api/v1/daemon/shutdown",
            headers={"X-Coffer-Token": info["token"]},
            timeout=5,
        )
        assert done.status_code == 204
        assert _wait(lambda: proc.poll() is not None, 60), "the daemon did not exit"
        assert not daemon_json.exists(), "daemon.json outlived the daemon"
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
        log.close()

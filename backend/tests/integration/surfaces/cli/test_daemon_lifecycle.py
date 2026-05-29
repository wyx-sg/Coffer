import subprocess
import sys
import time

import httpx
import pytest


@pytest.mark.timeout(30)
def test_start_then_status_then_stop(tmp_path, monkeypatch):
    """Full lifecycle: start (detached) → status reports ready → stop removes daemon.json."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "58100")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "58109")

    py = sys.executable
    # start
    r = subprocess.run(
        [py, "-m", "coffer.surfaces.cli.main", "daemon", "start"],
        capture_output=True,
        text=True,
        timeout=15,
        env={**__import__("os").environ},
    )
    assert r.returncode == 0, f"start failed: {r.stderr}"

    # poll until ready
    json_path = tmp_path / ".coffer" / "daemon.json"
    deadline = time.time() + 10
    while time.time() < deadline:
        if json_path.exists():
            break
        time.sleep(0.1)
    assert json_path.exists(), "daemon.json not written"

    import json

    info = json.loads(json_path.read_text())
    assert info["port"] in range(58100, 58110)
    token = info["token"]

    # status via HTTP
    deadline = time.time() + 10
    last_err = None
    while time.time() < deadline:
        try:
            res = httpx.get(
                f"http://127.0.0.1:{info['port']}/api/v1/daemon/status",
                headers={"X-Coffer-Token": token},
                timeout=2,
            )
            if res.status_code == 200 and res.json()["status"] == "ready":
                break
        except Exception as e:
            last_err = e
        time.sleep(0.2)
    else:
        pytest.fail(f"daemon never reported ready: {last_err}")

    # status via CLI
    r = subprocess.run(
        [py, "-m", "coffer.surfaces.cli.main", "daemon", "status"],
        capture_output=True,
        text=True,
        timeout=10,
        env={**__import__("os").environ},
    )
    assert r.returncode == 0
    assert "ready" in r.stdout

    # stop
    r = subprocess.run(
        [py, "-m", "coffer.surfaces.cli.main", "daemon", "stop"],
        capture_output=True,
        text=True,
        timeout=10,
        env={**__import__("os").environ},
    )
    assert r.returncode == 0
    # wait for daemon.json to be cleaned up
    deadline = time.time() + 5
    while time.time() < deadline and json_path.exists():
        time.sleep(0.1)
    assert not json_path.exists(), "daemon.json was not cleaned up after stop"

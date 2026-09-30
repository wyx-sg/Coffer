"""POST /resources/mcp_server/test-config and the enriched POST /{uid}/test, on the full app.

Spec mcp-gateway "Test an unsaved server config before adding it" and "Report
what a test of a registered server found". The full app (``create_app``) runs
over a temp SQLite file, so "nothing persisted" is read back from the real
tables the daemon would have written.
"""

from __future__ import annotations

import socket
import sqlite3
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from coffer.domain.mcp.probe import REDACTED
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.mcp.config_test_routes import get_url_guard
from tests.fixtures.fake_mcp_server import start_http_fake

_TOKEN = "test-token-config-test"
_FIXTURES = Path(__file__).resolve().parents[4] / "fixtures"
_FAKE = str(_FIXTURES / "fake_mcp_server.py")
_FORKING = str(_FIXTURES / "forking_mcp_server.py")
_URL = "/api/v1/resources/mcp_server/test-config"


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path / "logs"))
    app = create_app()
    set_active_token(_TOKEN)
    headers = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}
    with TestClient(app, base_url="http://localhost", headers=headers) as c:
        yield c


def _count(db: Path, table: str) -> int:
    with sqlite3.connect(db) as conn:
        return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def _stdio(*args: str, **transport: object) -> dict[str, object]:
    return {
        "transport": {"type": "stdio", "command": sys.executable, "args": list(args), **transport}
    }


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a stdio config is tested without saving anything"
)
def test_a_stdio_config_is_tested_without_saving_anything(
    app_client: TestClient, tmp_path: Path
) -> None:
    db = tmp_path / "c.db"
    before = {
        t: _count(db, t) for t in ("resources", "mcp_server_health", "mcp_invocations", "audit_log")
    }
    body = _stdio(_FAKE, "--tools", "read", "write", "--resources", "file:///a", "--prompts", "p")
    r = app_client.post(_URL, json={**body, "name": "fs"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True
    assert [t["name"] for t in out["tools"]] == ["read", "write"]
    assert (out["tool_count"], out["resource_count"], out["prompt_count"]) == (2, 1, 1)
    assert out["error_code"] is None
    after = {t: _count(db, t) for t in before}
    assert after == before
    assert (
        app_client.get("/api/v1/resources", params={"kind": "mcp_server"}).json()["resources"] == []
    )


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a failed test shows the exit code and the redacted stderr tail"
)
def test_a_failed_test_shows_the_exit_code_and_the_redacted_stderr_tail(
    app_client: TestClient,
) -> None:
    script = (
        "import os,sys; sys.stderr.write('bad key ' + os.environ['API_KEY'] + '\\n'); sys.exit(3)"
    )
    r = app_client.post(
        _URL, json={**_stdio("-c", script), "secret_values": {"API_KEY": "typed-secret-42"}}
    )
    out = r.json()
    assert out["ok"] is False
    assert out["error_code"] == "exited"
    assert out["exit_code"] == 3
    assert out["stderr_tail"] == [f"bad key {REDACTED}"]
    assert "typed-secret-42" not in r.text


def test_a_missing_command_is_spawn_failed(app_client: TestClient) -> None:
    r = app_client.post(
        _URL, json={"transport": {"type": "stdio", "command": "coffer-no-such-cmd"}}
    )
    assert r.json()["error_code"] == "spawn_failed"


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a config citing a stored secret is not started"
)
def test_a_config_citing_a_stored_secret_is_not_started(
    app_client: TestClient, tmp_path: Path
) -> None:
    marker = tmp_path / "started"
    body = _stdio(
        "-c", f"open({str(marker)!r}, 'w').write('x')", secret_refs={"GITHUB_TOKEN": "mcp/gh/t"}
    )
    out = app_client.post(_URL, json=body).json()
    assert out["error_code"] == "stored_secret_not_released"
    assert out["unreleased_secret_keys"] == ["GITHUB_TOKEN"]
    assert "GITHUB_TOKEN" in out["error_message"]
    time.sleep(0.2)
    assert not marker.exists()


class _Listener:
    """A loopback TCP port that counts the connections it is offered."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.sock.settimeout(0.1)
        self.accepted = 0
        self._stop = False
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    @property
    def port(self) -> int:
        return int(self.sock.getsockname()[1])

    def _run(self) -> None:
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            self.accepted += 1
            conn.close()

    def close(self) -> None:
        self._stop = True
        self._t.join(timeout=2)
        self.sock.close()


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a typed private URL is refused before any request"
)
def test_a_typed_private_url_is_refused_before_any_request(app_client: TestClient) -> None:
    listener = _Listener()
    try:
        r = app_client.post(
            _URL,
            json={"transport": {"type": "http", "url": f"http://127.0.0.1:{listener.port}/mcp"}},
        )
        time.sleep(0.2)
    finally:
        listener.close()
    out = r.json()
    assert out["error_code"] == "url_refused"
    assert "once it is added" in out["error_message"]
    assert listener.accepted == 0


def test_an_http_config_is_tested_when_the_guard_allows_it(app_client: TestClient) -> None:
    proc, port = start_http_fake(["ping"])
    app_client.app.dependency_overrides[get_url_guard] = lambda: lambda _url: None  # type: ignore[attr-defined]
    try:
        out = app_client.post(
            _URL,
            json={
                "transport": {"type": "http", "url": f"http://127.0.0.1:{port}/mcp"},
                "secret_values": {"X-Api-Key": "hdr-secret"},
            },
        ).json()
    finally:
        app_client.app.dependency_overrides.pop(get_url_guard, None)  # type: ignore[attr-defined]
        proc.terminate()
        proc.wait(timeout=5)
    assert out["ok"] is True, out
    assert [t["name"] for t in out["tools"]] == ["ping"]


def _gone(pid: int) -> bool:
    import os

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a test past its time limit stops the server's whole process group"
)
def test_a_test_past_its_time_limit_stops_the_whole_process_group(
    app_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import coffer.infrastructure.mcp.probe as probe

    monkeypatch.setattr(probe, "PROBE_TOTAL_SECONDS", 5.0)
    pidfile = tmp_path / "grandchild.pid"
    body = _stdio(_FORKING, str(pidfile), "serve", "--scenario", "slow", "--init-delay-ms", "60000")
    out = app_client.post(_URL, json=body).json()
    assert out["error_code"] == "timeout"
    assert _gone(int(pidfile.read_text()))


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a registered server's test lists its tools and records its health"
)
def test_a_registered_servers_test_lists_its_tools_and_records_its_health(
    app_client: TestClient,
) -> None:
    created = app_client.post(
        "/api/v1/resources",
        json={"kind": "mcp_server", "name": "fs", "config": _stdio(_FAKE, "--tools", "a", "b")},
    )
    assert created.status_code == 201, created.text
    uid = created.json()["uid"]
    out = app_client.post(f"/api/v1/resources/mcp_server/{uid}/test").json()
    assert out["ok"] is True
    assert [t["name"] for t in out["tools"]] == ["a", "b"]
    assert out["tool_count"] == 2
    assert out["server_capabilities"] is not None
    status = app_client.get(f"/api/v1/resources/mcp_server/{uid}/status").json()
    assert status["status"] == "healthy"


def test_a_registered_servers_failed_test_reports_the_exit_code(app_client: TestClient) -> None:
    created = app_client.post(
        "/api/v1/resources",
        json={
            "kind": "mcp_server",
            "name": "bad",
            "config": _stdio("-c", "import sys; sys.exit(1)"),
        },
    )
    uid = created.json()["uid"]
    out = app_client.post(f"/api/v1/resources/mcp_server/{uid}/test").json()
    assert (out["ok"], out["error_code"], out["exit_code"]) == (False, "exited", 1)
    assert (
        app_client.get(f"/api/v1/resources/mcp_server/{uid}/status").json()["status"] == "failing"
    )


def test_the_full_app_serves_the_builtin_server_without_a_resource_row(
    app_client: TestClient,
) -> None:
    body = app_client.get("/api/v1/mcp/builtin").json()
    assert body["name"] == "coffer"
    assert "coffer__search_tools" in [t["qualified_name"] for t in body["tools"]]
    assert body["connected_agent_uids"] == []
    resources = app_client.get("/api/v1/resources", params={"kind": "mcp_server"}).json()
    assert resources["resources"] == []

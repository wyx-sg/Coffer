"""`coffer daemon status` is read-only: with no daemon running it reports
"not running" and exits 3, and never spawns one."""

import json

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli import _client as cli_client
from coffer.surfaces.cli.main import app


@pytest.fixture
def no_daemon(tmp_path, monkeypatch):
    """An empty HOME, with every spawn path turned into a test failure."""
    monkeypatch.setenv("HOME", str(tmp_path))
    spawned: list[str] = []

    def _record_spawn():
        spawned.append("spawn")
        return None

    monkeypatch.setattr(cli_client, "_spawn_daemon", _record_spawn)
    monkeypatch.setattr(cli_client, "_DAEMON_BOOT_TIMEOUT", 0.05)
    return tmp_path, spawned


@pytest.mark.acceptance(
    spec="daemon", scenario="status reports a stopped daemon without starting one"
)
def test_status_without_a_daemon_says_not_running_and_spawns_nothing(no_daemon):
    home, spawned = no_daemon
    res = CliRunner().invoke(app, ["daemon", "status"])
    assert res.exit_code == 3
    assert res.stdout.splitlines() == ["status:  not running"]
    assert spawned == []
    assert not (home / ".coffer" / "daemon.json").exists()


def test_status_json_without_a_daemon_reports_stopped(no_daemon):
    _home, spawned = no_daemon
    res = CliRunner().invoke(app, ["daemon", "status", "--json"])
    assert res.exit_code == 3
    assert json.loads(res.stdout) == {"status": "stopped"}
    assert spawned == []


def test_status_treats_a_stale_daemon_json_as_not_running(no_daemon):
    """A daemon.json whose port nothing answers on is a crashed daemon."""
    home, spawned = no_daemon
    (home / ".coffer").mkdir()
    (home / ".coffer" / "daemon.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pid": 999999,
                "port": 1,
                "token": "t",
                "started_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )
    res = CliRunner().invoke(app, ["daemon", "status"])
    assert res.exit_code == 3
    assert "not running" in res.stdout
    assert spawned == []


# --- a running daemon: its channel and the passes in flight -----------------------


_TOKEN = "cli-status-token"


@pytest.fixture
def live_daemon(tmp_path, monkeypatch):
    """An in-process daemon serving ``/daemon/status`` and ``/upkeep/runs``."""
    from datetime import UTC, datetime

    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from coffer.infrastructure.daemon import phase
    from coffer.infrastructure.daemon.pid_lock import DaemonInfo
    from coffer.surfaces.http import errors as err_handlers
    from coffer.surfaces.http import feature_dependencies
    from coffer.surfaces.http.auth import set_active_token
    from coffer.surfaces.http.daemon_routes import router as daemon_router
    from coffer.surfaces.http.upkeep_routes import router as upkeep_router

    monkeypatch.setenv("HOME", str(tmp_path))
    prior = feature_dependencies._feature_service
    feature_dependencies.set_feature_service(feature_dependencies.build_feature_service())
    set_active_token(_TOKEN)
    # The phase is process-wide; an earlier test's shutdown may have left it
    # draining.
    monkeypatch.setattr(phase, "_PHASE", "ready")

    def _connect(**_kwargs):
        app = FastAPI()
        err_handlers.register(app)
        app.include_router(daemon_router)
        app.include_router(upkeep_router)
        client = TestClient(
            app,
            base_url="http://localhost/api/v1",
            headers={"X-Coffer-Token": _TOKEN},
            raise_server_exceptions=False,
        )
        info = DaemonInfo(
            version=1,
            pid=4242,
            port=38470,
            token=_TOKEN,
            started_at=datetime.now(tz=UTC),
        )
        return client, info

    monkeypatch.setattr(cli_client, "client_or_exit", _connect)
    monkeypatch.setattr(cli_client, "daemon_is_running", lambda: True)
    yield
    set_active_token(None)
    feature_dependencies._feature_service = prior


def test_status_prints_no_channel(live_daemon):
    res = CliRunner().invoke(app, ["daemon", "status"])
    assert res.exit_code == 0, res.output
    assert not [line for line in res.stdout.splitlines() if line.startswith("channel")]


@pytest.mark.acceptance(spec="daemon", scenario="status names the passes in flight")
@pytest.mark.acceptance(
    spec="resource-framework", scenario="the command line reads the passes in flight"
)
def test_status_names_the_passes_in_flight(live_daemon):
    """Both passes, oldest first, with kind, target and start time under
    ``--json``; once they end, the table's passes section says none is running.
    Neither call starts a pass: the registry holds exactly what the test put
    there."""
    from coffer.application.upkeep_runs import UPKEEP_RUNS

    assert UPKEEP_RUNS.claim("knowledge", "shopee") is True
    assert UPKEEP_RUNS.claim("memory", "coffer") is True
    try:
        as_json = CliRunner().invoke(app, ["daemon", "status", "--json"])
        during = CliRunner().invoke(app, ["daemon", "status"], env={"COLUMNS": "200"})
        assert {(r.kind, r.name) for r in UPKEEP_RUNS.list_running()} == {
            ("knowledge", "shopee"),
            ("memory", "coffer"),
        }
    finally:
        UPKEEP_RUNS.release("knowledge", "shopee")
        UPKEEP_RUNS.release("memory", "coffer")

    assert as_json.exit_code == 0, as_json.output
    payload = json.loads(as_json.stdout)
    assert payload["status"] == "ready"
    runs = payload["passes_in_flight"]
    assert [(r["kind"], r["name"]) for r in runs] == [("knowledge", "shopee"), ("memory", "coffer")]
    assert all(r["started_at"] for r in runs)
    assert runs[0]["started_at"] <= runs[1]["started_at"]

    assert during.exit_code == 0, during.output
    lines = during.stdout.splitlines()
    section = lines[lines.index("passes in flight:") + 1 :]
    assert "knowledge" in section[0] and "shopee" in section[0]
    assert "memory" in section[1] and "coffer" in section[1]

    after = CliRunner().invoke(app, ["daemon", "status"])
    assert after.exit_code == 0, after.output
    lines = after.stdout.splitlines()
    assert lines[lines.index("passes in flight:") + 1].strip() == "no pass is running"
    assert UPKEEP_RUNS.list_running() == []

    as_json = CliRunner().invoke(app, ["daemon", "status", "--json"])
    assert json.loads(as_json.stdout)["passes_in_flight"] == []


@pytest.mark.acceptance(spec="daemon", scenario="the status probe carries what the shell shows")
def test_the_status_probe_carries_what_the_shell_shows(live_daemon, monkeypatch):
    """Every fact the footer, Settings > Daemon and About show comes from the one
    tokenless probe, and ``coffer daemon status --json`` agrees with it."""
    import os

    from coffer.surfaces.http import daemon_port

    monkeypatch.setattr(daemon_port, "_PORT", 38470)
    client, _info = cli_client.client_or_exit()
    with client:
        r = client.get("/daemon/status", headers={"X-Coffer-Token": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["port"] == 38470
    assert body["started_at"]
    assert body["version"]
    assert body["executable"]
    assert "channel" not in body
    assert body["pid"] == os.getpid()
    # A build from source carries no commit; the key is still answered.
    assert "commit" in body
    assert body["data_dir"] == "~/.coffer"
    assert "connected_agents" in body

    res = CliRunner().invoke(app, ["daemon", "status", "--json"])
    assert res.exit_code == 0, res.output
    cli = json.loads(res.stdout)
    assert (cli["version"], cli["port"]) == (body["version"], body["port"])


@pytest.mark.acceptance(spec="daemon", scenario="the command line prints loop lag and task crashes")
def test_status_prints_loop_lag_and_task_crashes(live_daemon):
    from coffer.application.runtime import loop_lag
    from coffer.application.runtime.supervisor import tasks

    loop_lag.probe().record(0.0021)
    res = CliRunner().invoke(app, ["daemon", "status"], env={"COLUMNS": "200"})
    assert res.exit_code == 0, res.output
    lines = res.stdout.splitlines()
    [lag] = [line for line in lines if line.startswith("loop lag:")]
    assert "p99" in lag and "ms" in lag and "(last 300s)" in lag
    [count] = [line for line in lines if line.startswith("tasks:")]
    assert f"{tasks().stats().crashes} crashed" in count

    as_json = json.loads(CliRunner().invoke(app, ["daemon", "status", "--json"]).stdout)
    assert as_json["runtime"]["loop_lag_samples"] >= 1
    assert as_json["runtime"]["task_crashes"] == tasks().stats().crashes


@pytest.mark.acceptance(spec="daemon", scenario="the command line lists running tasks by name")
def test_status_tasks_lists_running_tasks_by_name(live_daemon, monkeypatch):
    from coffer.application.runtime.supervisor import tasks

    monkeypatch.setattr(
        tasks(), "running_by_name", lambda: {"reconciler": 1, "seatalk-ws": 2, "turn": 2}
    )
    plain = CliRunner().invoke(app, ["daemon", "status"], env={"COLUMNS": "200"})
    assert plain.exit_code == 0, plain.output
    assert "seatalk-ws" not in plain.stdout

    res = CliRunner().invoke(app, ["daemon", "status", "--tasks"], env={"COLUMNS": "200"})
    assert res.exit_code == 0, res.output
    lines = res.stdout.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("tasks:")) + 1
    # An earlier test in this process may have left a crash to report.
    start += lines[start].lstrip().startswith("last crash:")
    listed = [line.split() for line in lines[start : start + 3]]
    assert listed == [["seatalk-ws", "2"], ["turn", "2"], ["reconciler", "1"]]

    as_json = json.loads(CliRunner().invoke(app, ["daemon", "status", "--json"]).stdout)
    assert as_json["runtime"]["tasks_by_name"] == {"reconciler": 1, "seatalk-ws": 2, "turn": 2}


def _fake_daemon_pair(home):
    """A process pair that looks like a one-file daemon of ``home``'s vault: a
    shell parent and a Python child, both naming the daemon entry module."""
    import os
    import subprocess
    import sys

    child = (
        f"{sys.executable} -c 'import time; print(\"ready\", flush=True); time.sleep(60)' "
        "coffer.infrastructure.daemon.entry"
    )
    proc = subprocess.Popen(
        ["/bin/sh", "-c", f"{child}; : coffer.infrastructure.daemon.entry"],
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "HOME": str(home)},
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "ready"
    return proc


@pytest.mark.acceptance(spec="daemon", scenario="status names other daemon processes of the vault")
def test_status_names_another_daemon_process_of_the_vault_once(live_daemon, tmp_path):
    import psutil

    proc = _fake_daemon_pair(tmp_path)
    try:
        [child] = psutil.Process(proc.pid).children()
        as_json = CliRunner().invoke(app, ["daemon", "status", "--json"])
        table = CliRunner().invoke(app, ["daemon", "status"], env={"COLUMNS": "200"})
    finally:
        for p in psutil.Process(proc.pid).children(recursive=True):
            p.kill()
        proc.kill()
        proc.wait()

    assert as_json.exit_code == 0, as_json.output
    # The pair counts once — the child, never its shell parent — and the
    # serving daemon (pid 4242 here) is not "other".
    assert json.loads(as_json.stdout)["other_daemon_pids"] == [child.pid]
    [line] = [x for x in table.stdout.splitlines() if x.startswith("other daemon processes")]
    assert str(child.pid) in line


def test_status_names_no_other_daemon_when_there_is_none(live_daemon):
    res = CliRunner().invoke(app, ["daemon", "status", "--json"])
    assert json.loads(res.stdout)["other_daemon_pids"] == []
    table = CliRunner().invoke(app, ["daemon", "status"])
    assert not [x for x in table.stdout.splitlines() if x.startswith("other daemon")]


@pytest.mark.acceptance(spec="daemon", scenario="the command line lists each worker's schedule")
def test_status_workers_lists_each_worker(live_daemon, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from coffer.application.runtime.workers import WorkerMode, WorkerRecord, workers

    now = datetime.now(tz=UTC)
    rows = [
        WorkerRecord(
            name="reconciler",
            mode=WorkerMode.EVENT_FALLBACK,
            runs=3,
            last_started_at=now,
            last_duration_ms=12.5,
            last_ok=True,
            next_run_at=now + timedelta(seconds=120),
        ),
        WorkerRecord(name="usage-ingest", mode=WorkerMode.ON_DEMAND, state="parked"),
    ]
    monkeypatch.setattr(workers(), "snapshot", lambda: rows)
    plain = CliRunner().invoke(app, ["daemon", "status"], env={"COLUMNS": "200"})
    assert plain.exit_code == 0, plain.output
    assert "usage-ingest" not in plain.stdout

    res = CliRunner().invoke(app, ["daemon", "status", "--workers"], env={"COLUMNS": "200"})
    assert res.exit_code == 0, res.output
    lines = res.stdout.splitlines()
    start = lines.index("workers:") + 1
    reconciler, ingest = (line.split() for line in lines[start : start + 2])
    assert reconciler[:6] == ["reconciler", "event+fallback", "waiting", "3", "runs", "last"]
    assert "12.5" in reconciler and "ok" in reconciler
    assert reconciler[-3:-1] == ["next", "in"]
    assert 115 <= int(reconciler[-1].rstrip("s")) <= 120
    assert ingest == ["usage-ingest", "on-demand", "parked", "0", "runs"]

    as_json = json.loads(CliRunner().invoke(app, ["daemon", "status", "--json"]).stdout)
    assert [w["name"] for w in as_json["runtime"]["workers"]] == ["reconciler", "usage-ingest"]

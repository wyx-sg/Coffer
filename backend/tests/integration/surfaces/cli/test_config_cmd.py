"""``coffer config list|get|set|unset`` over the key registry.

The daemon-backed families run against the real app (``_real_app``), so a key
is shown to have the same effect and leave the same audit entry as the route
that stores it. ``daemon.port`` runs with no daemon at all.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon import config as daemon_config
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.main import app as cli_app

from ._real_app import audit, boot, extract_json

_runner = CliRunner()


@pytest.fixture
def daemon(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from boot(tmp_path, monkeypatch)


def _run(*args: str) -> Any:
    return _runner.invoke(cli_app, list(args), env={"COLUMNS": "250"})


def _provider(http: TestClient, name: str) -> str:
    r = http.post(
        "/providers",
        json={
            "name": name,
            "protocol": "anthropic",
            "base_url": f"https://{name}.example/anthropic",
            "secret_value": "sk-test-value",
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


def _flags(http: TestClient) -> dict[str, tuple[bool, bool]]:
    rows = http.get("/providers").json()["providers"]
    return {p["name"]: (p["internal_default"], p["transcribe_default"]) for p in rows}


# --- daemon.port: no daemon at all ---------------------------------------------------


@pytest.fixture
def no_daemon(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("HOME", str(tmp_path))

    def _refuse() -> Any:
        raise AssertionError("daemon.port must not reach for a daemon")

    monkeypatch.setattr(_cli_client, "client_or_exit", _refuse)
    monkeypatch.setattr(bootstrap, "live_daemon", lambda: None)
    return tmp_path


@pytest.mark.acceptance(
    spec="daemon", scenario="the port key is read and changed with no daemon running"
)
@pytest.mark.acceptance(
    spec="resource-framework", scenario="a setting is read, changed and returned to its default"
)
def test_the_port_key_is_read_changed_and_unset_with_no_daemon(no_daemon: Any) -> None:
    config_file = no_daemon / ".coffer" / "daemon-config.json"

    first = _run("config", "get", "daemon.port")
    assert first.exit_code == 0, first.output
    assert first.output.strip() == "8000"

    changed = _run("config", "set", "daemon.port", "8123")
    assert changed.exit_code == 0, changed.output
    assert json.loads(config_file.read_text())["port"] == 8123
    assert daemon_config.read_fixed_port() == 8123
    assert _run("config", "get", "daemon.port").output.strip() == "8123"

    back = _run("config", "unset", "daemon.port")
    assert back.exit_code == 0, back.output
    assert json.loads(config_file.read_text()).get("port") is None
    assert _run("config", "get", "daemon.port").output.strip() == "8000"

    listed = _run("config", "list", "daemon.", "--json")
    assert listed.exit_code == 0, listed.output
    [row] = json.loads(listed.output)["settings"]
    assert row["key"] == "daemon.port" and row["value"] == 8000 and row["default"] == 8000
    assert row["type"] == "port" and row["help"]
    table = _run("config", "list", "daemon.")
    assert "daemon.port" in table.output and "8000" in table.output


def test_the_port_key_refuses_an_unbindable_port(no_daemon: Any) -> None:
    r = _run("config", "set", "daemon.port", "80")
    assert r.exit_code == 6
    assert "between 1024 and 65535" in r.output
    assert daemon_config.read_fixed_port() is None


# --- refusals ------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="resource-framework", scenario="an invalid setting is refused before any write"
)
def test_an_invalid_setting_is_refused_before_any_write(daemon: TestClient) -> None:
    def days() -> dict[str, Any]:
        rows = daemon.get("/retention/policies").json()["policies"]
        return {p["table_name"]: p["retention_days"] for p in rows}

    before = days()
    alpha = _provider(daemon, "alpha")
    assert daemon.post(f"/providers/{alpha}/internal-default").status_code == 200
    flags_before = _flags(daemon)

    wrong_type = _run("config", "set", "retention.mcp_invocations", "soon")
    assert wrong_type.exit_code != 0
    assert "whole number of days" in wrong_type.output and "forever" in wrong_type.output

    unknown = _run("config", "set", "no.such.key", "1")
    assert unknown.exit_code != 0 and "no.such.key" in unknown.output

    no_default = _run("config", "unset", "engine.provider")
    assert no_default.exit_code != 0
    assert "coffer config set engine.provider" in no_default.output

    assert days() == before
    assert _flags(daemon) == flags_before
    assert audit(daemon, "retention_updated") == []


def test_an_unknown_pass_is_an_unknown_key(daemon: TestClient) -> None:
    r = _run("config", "set", "engine.upkeep.tidy.enabled", "off")
    assert r.exit_code == 4 and "engine.upkeep.tidy.enabled" in r.output


# --- engine.* and transcribe.* ------------------------------------------------------


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="the command line lists every engine setting under one namespace",
)
def test_engine_and_transcribe_keys_share_one_namespace(daemon: TestClient) -> None:
    uid = _provider(daemon, "alpha")
    assert daemon.post(f"/providers/{uid}/internal-default").status_code == 200
    assert _run("config", "set", "engine.model", "picked-model").exit_code == 0

    engine = _run("config", "list", "engine.", "--json")
    assert engine.exit_code == 0, engine.output
    rows = {r["key"]: r for r in extract_json(engine.output)["settings"]}
    passes = {
        f"engine.upkeep.{p}.{f}"
        for p in ("aggregate", "distil", "curate")
        for f in ("enabled", "interval")
    }
    assert set(rows) == {
        "engine.provider",
        "engine.model",
        "engine.timeout",
        "engine.curate_owner",
        *passes,
    }
    assert rows["engine.provider"]["value"] == "alpha"
    assert rows["engine.model"]["value"] == "picked-model"
    assert rows["engine.timeout"]["value"] is None and rows["engine.timeout"]["default"] > 0
    assert rows["engine.upkeep.aggregate.interval"]["default"] == 3600
    assert all(r["help"] for r in rows.values())

    transcribe = _run("config", "list", "transcribe.", "--json")
    assert {r["key"] for r in extract_json(transcribe.output)["settings"]} == {
        "transcribe.provider",
        "transcribe.model",
    }


def test_engine_model_timeout_and_upkeep_round_trip(daemon: TestClient) -> None:
    assert "no engine model chosen" in _run("config", "get", "engine.model").output
    assert _run("config", "set", "engine.model", "m1").exit_code == 0
    assert daemon.get("/internal-engine-config").json()["model"] == "m1"
    events = audit(daemon, "internal_engine_model_set")
    assert events and events[0]["actor"] == "cli"
    assert _run("config", "unset", "engine.model").exit_code == 0
    assert daemon.get("/internal-engine-config").json()["model"] is None

    assert "default (" in _run("config", "get", "engine.timeout").output
    assert _run("config", "set", "engine.timeout", "120").exit_code == 0
    assert "120s (default" in _run("config", "get", "engine.timeout").output
    assert _run("config", "unset", "engine.timeout").exit_code == 0
    assert daemon.get("/internal-engine-config").json()["model_timeout_s"] is None

    assert _run("config", "set", "engine.upkeep.curate.enabled", "off").exit_code == 0
    assert _run("config", "set", "engine.upkeep.distil.interval", "900").exit_code == 0
    upkeep = daemon.get("/internal-engine-config").json()["upkeep"]
    assert upkeep["curate"]["enabled"] is False and upkeep["distil"]["interval_s"] == 900
    assert _run("config", "unset", "engine.upkeep.distil.interval").exit_code == 0
    assert _run("config", "unset", "engine.upkeep.curate.enabled").exit_code == 0
    upkeep = daemon.get("/internal-engine-config").json()["upkeep"]
    assert upkeep["curate"]["enabled"] is True and upkeep["distil"]["interval_s"] is None

    assert _run("config", "set", "transcribe.model", "whisper-1").exit_code == 0
    assert daemon.get("/internal-engine-config").json()["transcribe_model"] == "whisper-1"


def test_curate_owner_names_this_machine_and_clears(daemon: TestClient) -> None:
    first = _run("config", "get", "engine.curate_owner")
    assert first.exit_code == 0, first.output
    assert "curation owner: none" in first.output
    assert "(this machine)" in _run("config", "set", "engine.curate_owner", "this").output
    body = extract_json(_run("config", "get", "engine.curate_owner", "--json").output)
    assert body["state"] == "self" and body["curate_owner_machine_id"] == body["this_machine_id"]
    assert "curation owner: none" in _run("config", "unset", "engine.curate_owner").output
    assert daemon.get("/internal-engine-config").json()["curate_owner_machine_id"] is None


# --- the two connection flags -----------------------------------------------------------


@pytest.mark.acceptance(
    spec="provider-switching", scenario="the command line names the internal engine's connection"
)
def test_engine_provider_moves_the_flag_and_refuses_unset(daemon: TestClient) -> None:
    alpha = _provider(daemon, "alpha")
    _provider(daemon, "beta")
    assert daemon.post(f"/providers/{alpha}/internal-default").status_code == 200

    moved = _run("config", "set", "engine.provider", "beta")
    assert moved.exit_code == 0, moved.output
    assert _flags(daemon)["beta"][0] is True and _flags(daemon)["alpha"][0] is False
    assert any(e["resource_name"] == "beta" for e in audit(daemon, "provider_internal_default_set"))
    assert _run("config", "get", "engine.provider").output.strip().endswith("beta")

    refused = _run("config", "unset", "engine.provider")
    assert refused.exit_code != 0
    assert "naming another connection" in refused.output
    assert _flags(daemon)["beta"][0] is True


@pytest.mark.acceptance(
    spec="provider-switching", scenario="the command line names the speech-to-text connection"
)
def test_transcribe_provider_moves_only_its_own_flag(daemon: TestClient) -> None:
    a = _provider(daemon, "conn-a")
    _provider(daemon, "conn-b")
    assert daemon.post(f"/providers/{a}/internal-default").status_code == 200
    assert daemon.post(f"/providers/{a}/transcribe-default").status_code == 200

    moved = _run("config", "set", "transcribe.provider", "conn-b")
    assert moved.exit_code == 0, moved.output
    assert _flags(daemon)["conn-b"] == (False, True)
    assert _flags(daemon)["conn-a"] == (True, False)
    assert _run("config", "get", "transcribe.provider").output.strip().endswith("conn-b")
    assert any(
        e["resource_name"] == "conn-b" for e in audit(daemon, "provider_transcribe_default_set")
    )


# --- retention.<table> + log prune -----------------------------------------------


def _seed_invocations(ages_days: list[int]) -> None:
    from coffer.domain.mcp.capability import MCPInvocation
    from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
    from coffer.infrastructure.persistence.engine import (
        create_async_engine_with_pragmas,
        session_maker,
    )

    engine = create_async_engine_with_pragmas(os.environ["COFFER_DB_URL"])

    async def _seed() -> None:
        repo = MCPInvocationRepo(session_maker(engine))
        for i, age in enumerate(ages_days):
            await repo.insert(
                MCPInvocation(
                    id=None,
                    timestamp=datetime.now(tz=UTC) - timedelta(days=age),
                    resource_uid="coffer",
                    capability_type="tool",
                    capability_key=f"call-{i}-{age}d",
                    duration_ms=1,
                    status="ok",
                    error_message=None,
                    session_id=None,
                )
            )
        await engine.dispose()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_seed())
    loop.close()


@pytest.mark.acceptance(
    spec="resource-framework", scenario="the command line sets a retention period and prunes now"
)
def test_retention_is_a_setting_and_prune_is_a_log_verb(daemon: TestClient) -> None:
    _seed_invocations([30, 10, 1])

    assert _run("config", "set", "retention.mcp_invocations", "7").exit_code == 0
    assert _run("config", "get", "retention.mcp_invocations").output.strip().endswith("7")
    assert any(e for e in audit(daemon, "retention_updated"))

    pruned = _run("log", "prune", "--table", "mcp_invocations")
    assert pruned.exit_code == 0, pruned.output
    assert "pruned mcp_invocations: 2 rows deleted" in pruned.output
    left = daemon.get("/mcp/invocations").json()["invocations"]
    assert [r["capability_key"] for r in left] == ["call-2-1d"]

    assert _run("config", "set", "retention.mcp_invocations", "forever").exit_code == 0
    policies = {p["table_name"]: p for p in daemon.get("/retention/policies").json()["policies"]}
    assert policies["mcp_invocations"]["retention_days"] is None
    assert _run("config", "unset", "retention.mcp_invocations").exit_code == 0
    policies = {p["table_name"]: p for p in daemon.get("/retention/policies").json()["policies"]}
    assert (
        policies["mcp_invocations"]["retention_days"]
        == policies["mcp_invocations"]["default_retention_days"]
    )

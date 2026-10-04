"""What a reconcile pass costs, over the real app — the measurement behind the
reconciler's period (``DEFAULT_PERIOD_SECONDS``) and its per-pass budget
(``PASS_BUDGET_SECONDS``).

The setup is a heavy single-user machine: two agents (Claude Code and Codex),
both connected (MCP entry + memory hook), twenty skills delivered to both, and
an active provider connection projected into both. A steady-state pass — every
target reads everything and finds nothing to do — is timed, and so is the
dry-run plan the drift view reads.

Measured 2026-09-29 on an Apple-silicon laptop: a steady-state pass costs about
27 ms (median of 30) and the dry-run plan the same, far inside the 2 s budget,
so the 60 s period is set by how long drift may stand unnoticed rather than by
cost. The budget asserted below is
the logged budget, not the measured value: it fails when a target starts doing
work in proportion to something it should not.

Marked ``benchmark`` (excluded from ``make verify``; ``make verify-benchmark``).
"""

from __future__ import annotations

import os
import pathlib
import statistics
import time
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from coffer.application.reconcile.reconciler import PASS_BUDGET_SECONDS
from coffer.domain.reconcile import Trigger
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.reconcile_dependencies import get_reconciler
from tests.fixtures.keyring import install_in_memory_keyring

pytestmark = pytest.mark.benchmark

_TOKEN = "test-token-reconcile-cost"
_SKILLS = 20
_RUNS = 30


def _should_run() -> bool:
    return os.environ.get("COFFER_RUN_BENCHMARKS") == "1"


@pytest.fixture
def machine(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    install_in_memory_keyring(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("COFFER_FEATURES", "knowledge=on,memory=on,models=on,sync=off")
    shim = tmp_path / "bin" / "coffer-mcp-shim"
    shim.parent.mkdir()
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(shim))
    for d in (".claude", ".codex"):
        (tmp_path / d).mkdir()
    set_active_token(_TOKEN)
    try:
        with TestClient(create_app(), headers={"X-Coffer-Token": _TOKEN}) as c:
            for agent_type in ("claude_code", "codex"):
                r = c.post("/api/v1/agents", json={"type": agent_type})
                assert r.status_code == 201, r.text
                assert (
                    c.post(f"/api/v1/agents/{r.json()['uid']}/coffer-connection").status_code == 200
                )
            for n in range(_SKILLS):
                folder = tmp_path / "src" / f"skill-{n}"
                folder.mkdir(parents=True)
                (folder / "SKILL.md").write_text(
                    f"---\nname: skill-{n}\ndescription: Skill number {n}.\n---\n# {n}\n",
                    encoding="utf-8",
                )
                r = c.post("/api/v1/skills/import", json={"path": str(folder)})
                assert r.status_code == 201, r.text
            r = c.post(
                "/api/v1/providers",
                json={
                    "name": "gw",
                    "protocol": "anthropic",
                    "base_url": "https://gw/anthropic",
                    "secret_value": "sk-bench",
                },
            )
            assert r.status_code == 201, r.text
            assert (
                c.post(
                    f"/api/v1/providers/{r.json()['uid']}/activate",
                    json={"agent_type": "claude_code"},
                ).status_code
                == 200
            )
            yield c
    finally:
        set_active_token(None)


def _median_seconds(client: TestClient, call) -> float:  # type: ignore[no-untyped-def]
    samples = []
    for _ in range(_RUNS):
        start = time.perf_counter()
        client.portal.call(call)  # type: ignore[union-attr]
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


@pytest.mark.skipif(not _should_run(), reason="set COFFER_RUN_BENCHMARKS=1")
def test_a_steady_state_pass_stays_inside_the_budget(machine: TestClient) -> None:
    rec = get_reconciler()
    first = machine.portal.call(lambda: rec.run(trigger=Trigger.PERIOD))  # type: ignore[union-attr]
    # Steady state: nothing left to repair, so the timing is the reading cost.
    # What stays open is the person's to settle: a hook no trigger here
    # installs, and Codex's approval of Coffer's hook, which Coffer never gives.
    persons = {"hook_missing", "hook_untrusted"}
    assert [r for r in first.results if r.change.decision.reason_code not in persons] == []
    period = _median_seconds(machine, lambda: rec.run(trigger=Trigger.PERIOD))
    plan = _median_seconds(machine, lambda: rec.plan())
    print(f"\nreconcile pass median {period * 1000:.1f} ms, dry-run plan {plan * 1000:.1f} ms")
    assert period < PASS_BUDGET_SECONDS
    assert plan < PASS_BUDGET_SECONDS

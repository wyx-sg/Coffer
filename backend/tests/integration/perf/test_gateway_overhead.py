"""SC-003: gateway median overhead ≤ 50 ms per tool call.

Marked ``benchmark`` so it is excluded from default ``make verify`` runs.
Enable with ``pytest -m benchmark`` or set ``COFFER_RUN_BENCHMARKS=1``.
"""

from __future__ import annotations

import os
import statistics
import sys
import time
from pathlib import Path

import keyring
import keyring.core
import pytest

from coffer.application.audit_service import AuditService
from coffer.application.mcp.credential_resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.server_config import MCPServerConfig, StdioTransport
from coffer.domain.resource import Kind
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
)
from coffer.infrastructure.mcp.subprocess import StdioUpstreamConnection
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)

_FAKE = Path(__file__).resolve().parents[2] / "fixtures" / "fake_mcp_server.py"
_N_RUNS = 30
_MAX_OVERHEAD_MS = 50


class _InMemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1.0  # type: ignore[assignment]

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def get_password(self, s: str, u: str) -> str | None:
        return self._data.get((s, u))

    def set_password(self, s: str, u: str, p: str) -> None:
        self._data[(s, u)] = p

    def delete_password(self, s: str, u: str) -> None:
        self._data.pop((s, u), None)


def _should_run() -> bool:
    return os.environ.get("COFFER_RUN_BENCHMARKS") == "1"


pytestmark = pytest.mark.benchmark


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="gateway overhead stays under budget")
@pytest.mark.skipif(
    not _should_run(),
    reason="benchmark suite disabled by default; set COFFER_RUN_BENCHMARKS=1",
)
@pytest.mark.asyncio
async def test_gateway_overhead_under_50ms_median(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keyring.core, "_keyring_backend", _InMemoryKeyring())

    transport = StdioTransport(
        type="stdio",
        command=sys.executable,
        args=[str(_FAKE), "--scenario", "basic", "--tools", "ping"],
    )

    # ------------------------------------------------------------------ #
    # Baseline: direct connection — no gateway, no supervisor, no         #
    # discovery layer, no DB, no credential resolution.                   #
    # ------------------------------------------------------------------ #
    baseline_ms: list[float] = []
    direct = StdioUpstreamConnection(
        transport=transport,
        env_overlay={},
        server_name="bench",
    )
    await direct.spawn_and_initialize()
    try:
        # Warmup — establish steady-state subprocess + event-loop state.
        for _ in range(3):
            await direct.request("tools/call", {"name": "ping", "arguments": {}})
        for _ in range(_N_RUNS):
            t0 = time.perf_counter()
            await direct.request("tools/call", {"name": "ping", "arguments": {}})
            baseline_ms.append((time.perf_counter() - t0) * 1000)
    finally:
        await direct.close()

    # ------------------------------------------------------------------ #
    # Gateway path: MCPGatewaySession → SubprocessSupervisor →            #
    # StdioUpstreamConnection.                                            #
    # ------------------------------------------------------------------ #
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    rsvc = ResourceService(
        kinds={
            "mcp_server": Kind(
                name="mcp_server",
                display_name="MCP Server",
                config_schema=MCPServerConfig,
            )
        },
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    await rsvc.register(
        kind="mcp_server",
        name="bench",
        config={
            "transport": {
                "type": "stdio",
                "command": sys.executable,
                "args": [str(_FAKE), "--scenario", "basic", "--tools", "ping"],
            },
        },
        actor="bench",
    )

    supervisor = SubprocessSupervisor(
        resource_service=rsvc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    prefs = MCPCapabilityPreferenceRepo(sm)
    inv_repo = MCPInvocationRepo(sm)
    discovery = CapabilityDiscovery(
        resource_service=rsvc,
        supervisor=supervisor,
        preferences=prefs,
        audit=audit,
    )
    session = MCPGatewaySession(
        session_id="bench-session",
        resource_service=rsvc,
        supervisor=supervisor,
        discovery=discovery,
        preferences=prefs,
        invocations=inv_repo,
    )

    # Populate capability preferences so calls don't hit the discovery path.
    await session.handle_request("tools/list")

    gateway_ms: list[float] = []
    try:
        # Warmup
        for _ in range(3):
            await session.handle_request(
                "tools/call",
                {"name": "bench__ping", "arguments": {}},
            )
        for _ in range(_N_RUNS):
            t0 = time.perf_counter()
            await session.handle_request(
                "tools/call",
                {"name": "bench__ping", "arguments": {}},
            )
            gateway_ms.append((time.perf_counter() - t0) * 1000)
    finally:
        await session.dispose()
        await engine.dispose()

    baseline_median = statistics.median(baseline_ms)
    gateway_median = statistics.median(gateway_ms)
    overhead = gateway_median - baseline_median

    print(
        f"\nbaseline median: {baseline_median:.2f} ms\n"
        f"gateway median:  {gateway_median:.2f} ms\n"
        f"overhead median: {overhead:.2f} ms\n"
        f"limit:           {_MAX_OVERHEAD_MS} ms"
    )

    assert overhead <= _MAX_OVERHEAD_MS, (
        f"gateway overhead {overhead:.2f} ms exceeds the {_MAX_OVERHEAD_MS} ms "
        f"SC-003 budget (baseline {baseline_median:.2f} ms, gateway "
        f"{gateway_median:.2f} ms)"
    )

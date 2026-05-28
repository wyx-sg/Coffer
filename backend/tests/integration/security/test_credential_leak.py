"""SC-010: secret values must never appear in the DB, logs, or any persisted
artefact.

Drives a representative session with a unique sentinel value stored in the
in-memory keychain, then greps every persistable surface for the sentinel.
Zero occurrences are required — any hit fails the test with a precise pointer
to the surface where the leak was found.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import sys
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
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
)
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


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="credentials never leak to logs or audit")
@pytest.mark.asyncio
async def test_secret_value_never_in_db_or_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Unique sentinel — unguessable, collision-resistant for this test run.
    sentinel = f"COFFER_LEAK_SENTINEL_{secrets.token_hex(16)}"

    # Install in-memory keyring and store the sentinel under a ref key.
    monkeypatch.setattr(keyring.core, "_keyring_backend", _InMemoryKeyring())
    keyring.set_password("coffer", "leak-test-ref", sentinel)

    # Redirect coffer log files to a temp dir so we can grep them cleanly.
    db_path = tmp_path / "c.db"
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_LOG_DIR", str(log_dir))

    # ------------------------------------------------------------------ #
    # Build the full stack in-process.                                    #
    # ------------------------------------------------------------------ #
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
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

    # Register a server that references the credential via credential_refs.
    # The config stored in the DB contains the *ref key* ("leak-test-ref"),
    # never the actual sentinel value.
    await rsvc.register(
        kind="mcp_server",
        name="leak-test",
        config={
            "transport": {
                "type": "stdio",
                "command": sys.executable,
                "args": [
                    str(_FAKE),
                    "--scenario",
                    "basic",
                    "--tools",
                    "read_file",
                ],
                "credential_refs": {"GITHUB_TOKEN": "leak-test-ref"},
            },
        },
        actor="test",
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
        session_id="leak-session",
        resource_service=rsvc,
        supervisor=supervisor,
        discovery=discovery,
        preferences=prefs,
        invocations=inv_repo,
    )

    try:
        # Walk through every surface that touches credentials:
        # list → call → query audit + invocations.
        await session.handle_request("tools/list")
        await session.handle_request(
            "tools/call",
            {"name": "leak-test__read_file", "arguments": {"path": "/tmp/x"}},
        )
        audit_events = await audit.query()
        invocations = await inv_repo.query()
    finally:
        await session.dispose()
        await engine.dispose()

    # ------------------------------------------------------------------ #
    # Grep every persistable surface for the sentinel.                    #
    # ------------------------------------------------------------------ #

    def _check(surface_name: str, blob: str) -> None:
        if sentinel in blob:
            idx = blob.index(sentinel)
            context_start = max(0, idx - 80)
            context_end = min(len(blob), idx + 80)
            raise AssertionError(
                f"CREDENTIAL LEAK detected in {surface_name}!\n"
                f"Sentinel '{sentinel}' was found.\n"
                f"Context: ...{blob[context_start:context_end]}..."
            )

    # 1. SQLite DB — dump every cell of every table as a repr string.
    sync_conn = sqlite3.connect(db_path)
    try:
        cursor = sync_conn.cursor()
        tables = [
            row[0]
            for row in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        db_parts: list[str] = []
        for table in tables:
            for row in cursor.execute(f"SELECT * FROM {table}").fetchall():
                db_parts.append(repr(row))
        _check("sqlite DB", "\n".join(db_parts))
    finally:
        sync_conn.close()

    # 2. Audit query response — serialise all fields.
    _check(
        "audit query response",
        json.dumps(
            [
                {
                    "event_type": e.event_type,
                    "details": e.details,
                    "actor": e.actor,
                    "resource_kind": e.resource_kind,
                    "resource_name": e.resource_name,
                }
                for e in audit_events
            ],
            default=str,
        ),
    )

    # 3. Invocation query response — serialise all fields.
    _check(
        "invocations query response",
        json.dumps(
            [
                {
                    "capability_key": inv.capability_key,
                    "status": inv.status,
                    "error_message": inv.error_message,
                    "resource_name": inv.resource_name,
                    "session_id": inv.session_id,
                }
                for inv in invocations
            ],
            default=str,
        ),
    )

    # 4. Log files written by _attach_file_handler (Phase 9.1).
    for log_file in log_dir.rglob("*.log"):
        _check(f"log file '{log_file.name}'", log_file.read_text())

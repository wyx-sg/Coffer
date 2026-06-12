"""SC-010: secret values must never appear in the DB, logs, or any persisted
artefact.

Drives a representative session with a unique sentinel value written into the
Fernet-encrypted credential store (the same store the composition root wires),
then greps every persistable surface for the sentinel. Zero plaintext
occurrences are required — any hit fails the test with a precise pointer to the
surface where the leak was found. Because the secret now lives encrypted in the
``credentials`` table, the SQLite-bytes grep is REAL coverage: it proves the
ciphertext column never exposes plaintext while the value still round-trips.
"""

from __future__ import annotations

import contextlib
import json
import logging
import secrets
import sqlite3
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from coffer.application.audit_service import AuditService
from coffer.application.mcp.credential_resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import UpstreamUnavailable
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.infrastructure.logging.setup import _attach_file_handler
from coffer.infrastructure.mcp.factory import build_upstream
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


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="credentials never leak to logs or audit")
@pytest.mark.asyncio
async def test_secret_value_never_in_db_or_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Unique sentinel — unguessable, collision-resistant for this test run.
    sentinel = f"COFFER_LEAK_SENTINEL_{secrets.token_hex(16)}"

    # Redirect coffer log files to a temp dir so we can grep them cleanly, and
    # actually attach the rotating file handler so a daemon.log is produced —
    # otherwise the log-stream grep below is vacuous (no .log file to scan).
    db_path = tmp_path / "c.db"
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_LOG_DIR", str(log_dir))

    # Hermetic logging setup: other tests in the suite mutate global logging
    # state (configure_logging/structlog, caplog, logger.disabled, raised
    # levels), which previously left this test's daemon.log empty when it ran
    # after them. Defensively reset so the supervisor's spawn_failed WARNING is
    # guaranteed to reach our file handler regardless of test ordering.
    logging.disable(logging.NOTSET)  # undo any global logging.disable()
    root_logger = logging.getLogger()
    prev_root_level = root_logger.level
    root_logger.setLevel(logging.DEBUG)
    prev_states: list[tuple[logging.Logger, bool, int]] = []
    for name in ("", "coffer", "coffer.application.mcp.supervisor"):
        lg = logging.getLogger(name)
        prev_states.append((lg, lg.disabled, lg.level))
        lg.disabled = False
        lg.setLevel(logging.NOTSET if name else logging.DEBUG)
    handlers_before = set(root_logger.handlers)
    _attach_file_handler()  # writes <COFFER_LOG_DIR>/daemon.log
    added_handlers = [h for h in root_logger.handlers if h not in handlers_before]
    for h in added_handlers:
        h.setLevel(logging.DEBUG)

    # ------------------------------------------------------------------ #
    # Build the full stack in-process.                                    #
    # ------------------------------------------------------------------ #
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    # Write the sentinel through the Fernet-encrypted store — exactly the path
    # the composition root uses. The plaintext is encrypted into the
    # `credentials` table; only the in-memory decrypt below ever sees it as
    # cleartext, so the DB-bytes grep further down is real coverage.
    credential_store = EncryptedCredentialStore(db_path=db_path, key=Fernet.generate_key())
    credential_store.set("leak-test-ref", sentinel)
    assert credential_store.get("leak-test-ref") == sentinel  # round-trips

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

    # Also register a credentialed server that FAILS to spawn, so the
    # supervisor logs `mcp.upstream.spawn_failed` on the credential-bearing
    # path (where a naive impl would be most likely to leak the materialised
    # secret into the log line). retry_delays=() makes the failure instant.
    await rsvc.register(
        kind="mcp_server",
        name="leak-fail",
        config={
            "transport": {
                "type": "stdio",
                "command": "/nonexistent/coffer-leak-cmd",
                "args": [],
                "credential_refs": {"GITHUB_TOKEN": "leak-test-ref"},
            },
        },
        actor="test",
    )

    supervisor = SubprocessSupervisor(
        upstream_factory=build_upstream,
        resource_service=rsvc,
        credential_resolver=CredentialResolver(credential_store),
        retry_delays=(),
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
        # Force a logged failure on the credentialed path (materialises the
        # secret into the overlay, then fails to spawn → logs spawn_failed).
        with contextlib.suppress(UpstreamUnavailable):
            await supervisor.get_or_spawn("leak-fail")
        audit_events = await audit.query()
        invocations = await inv_repo.query()
    finally:
        await session.dispose()
        await engine.dispose()
        # Flush + detach the file handler so it neither buffers nor leaks into
        # other tests' root-logger state, and restore the logger levels/flags.
        for h in added_handlers:
            with contextlib.suppress(Exception):
                h.flush()
            root_logger.removeHandler(h)
        root_logger.setLevel(prev_root_level)
        for lg, was_disabled, level in prev_states:
            lg.disabled = was_disabled
            lg.setLevel(level)

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

    # 4. Log files written by _attach_file_handler (Phase 9.1). This step is
    #    only meaningful if a log file actually exists AND captured real
    #    activity — otherwise the grep would pass vacuously. Assert both.
    log_files = list(log_dir.rglob("*.log"))
    assert log_files, "no daemon.log was written — log-stream leak check would be vacuous"
    combined_logs = "\n".join(f.read_text() for f in log_files)
    assert combined_logs.strip(), "daemon.log is empty — log-stream leak check would be vacuous"
    # Prove the credential-bearing failure path actually logged (so the grep
    # below is exercised against the line most likely to leak a secret).
    assert "spawn_failed" in combined_logs, (
        "expected the credentialed spawn failure to be logged to daemon.log"
    )
    for log_file in log_files:
        _check(f"log file '{log_file.name}'", log_file.read_text())

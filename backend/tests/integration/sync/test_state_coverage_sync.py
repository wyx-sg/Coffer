"""Shared-intent state areas: MCP preferences + engine settings (spec 010 slice 7)."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from coffer.application.audit_service import AuditService
from coffer.application.embedding_config_service import EmbeddingConfigService
from coffer.application.engine_settings_sync import EngineSettingsSyncState
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.mcp.sync_state import McpPreferenceSyncState
from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceRepo
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyEmbeddingConfigRepo,
    SqlAlchemyInternalEngineConfigRepo,
)
from coffer.infrastructure.sync.git_repo import GitRepo

from .test_two_machine_sync import _make_machine


@pytest_asyncio.fixture
async def remote(tmp_path):  # type: ignore[no-untyped-def]
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    return bare


def _providers(resources, sm):  # type: ignore[no-untyped-def]
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    embedding_repo = SqlAlchemyEmbeddingConfigRepo(sm)
    internal_repo = SqlAlchemyInternalEngineConfigRepo(sm)
    embedding = EmbeddingConfigService(repo=embedding_repo, audit=audit, credentials=None)
    internal = InternalEngineConfigService(repo=internal_repo, audit=audit)
    return [
        McpPreferenceSyncState(resources, MCPCapabilityPreferenceRepo(sm)),
        EngineSettingsSyncState(
            embedding, internal, embedding_repo=embedding_repo, internal_repo=internal_repo
        ),
    ]


@pytest.mark.acceptance(spec="010-sync", scenario="shared preferences and engine settings sync")
async def test_mcp_preferences_and_engine_settings_round_trip(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine(
        "A", tmp_path / "A", remote, create_key=True, state_providers_factory=_providers
    )
    server = await a.resources.register("mcp_server", "confluence", {"value": "x"}, "test")
    prefs_a = MCPCapabilityPreferenceRepo(a.sm)
    now = datetime.now(tz=UTC)
    await prefs_a.insert(server.id, "tool", "dangerous_tool", False, now, now)
    internal_a = InternalEngineConfigService(
        repo=SqlAlchemyInternalEngineConfigRepo(a.sm),
        audit=AuditService(SqlAlchemyAuditRepo(a.sm)),
    )
    await internal_a.update(model="gpt-test", actor="test")
    await a.service.run()

    b = await _make_machine(
        "B", tmp_path / "B", remote, create_key=True, state_providers_factory=_providers
    )
    await b.service.run()

    # The disabled tool and the engine model both arrived on B.
    server_b = next(r for r in await b.resources.list() if r.name == "confluence")
    prefs_b = MCPCapabilityPreferenceRepo(b.sm)
    rows = await prefs_b.list_for(server_b.id)
    assert [(str(p.capability_type), p.capability_key, p.enabled) for p in rows] == [
        ("tool", "dangerous_tool", False)
    ]
    internal_b = InternalEngineConfigService(
        repo=SqlAlchemyInternalEngineConfigRepo(b.sm),
        audit=AuditService(SqlAlchemyAuditRepo(b.sm)),
    )
    assert (await internal_b.get()).model == "gpt-test"

    # B re-enables the tool; the re-enable propagates back to A.
    await prefs_b.set_enabled(server_b.id, "tool", "dangerous_tool", True)
    await b.service.run()
    await a.service.run()
    rows_a = await prefs_a.list_for(server.id)
    assert all(p.enabled for p in rows_a)


async def test_owned_prefix_never_crosses_sibling_names(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """Owning server "jira" must not delete "jira-internal"'s doc when that
    sibling is not held locally (review #288 finding 1)."""
    a = await _make_machine(
        "A", tmp_path / "A", remote, create_key=True, state_providers_factory=_providers
    )
    await a.resources.register("mcp_server", "jira", {"value": "x"}, "test")
    await a.service.run()

    # A foreign machine's doc for a sibling server A does not hold.
    sibling = a.root / "ws" / "state" / "mcp-preferences" / "jira-internal.yaml"
    sibling.parent.mkdir(parents=True, exist_ok=True)
    sibling.write_text(
        "disabled:\n- key: risky\n  type: tool\nserver: jira-internal\n", encoding="utf-8"
    )
    GitRepo(a.root / "ws").commit_all("foreign sibling doc")

    await a.service.run()
    files = a.workspace.list_files()
    assert "state/mcp-preferences/jira-internal.yaml" in files  # preserved

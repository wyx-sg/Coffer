"""The daemon starts on an upgraded home and serves what the old one held;
it refuses a home that was not upgraded rather than upgrading it itself."""

from __future__ import annotations

from typing import Any, cast

import pytest
from starlette.testclient import TestClient

from coffer.application.agent.kind import make_agent_kind
from coffer.application.channel.kind import make_channel_kind
from coffer.application.knowledge.kind import make_knowledge_kind
from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.memory.kind import make_memory_kind
from coffer.application.provider.kind import make_provider_kind
from coffer.application.skill.kind import make_skill_kind
from coffer.domain.resource import Kind
from coffer.infrastructure.persistence.migrations_runner import run_migrations
from coffer.infrastructure.vault.migration.classes import storage_of
from coffer.infrastructure.vault.migration.errors import MigrationRequired
from coffer.infrastructure.vault.migration.run import migrate

from .conftest import UPGRADE
from .legacy_home import UIDS, LegacyHome, resources

_TOKEN = "migration-token"


def test_the_daemon_lists_every_migrated_resource_with_its_reach(legacy: LegacyHome) -> None:
    from coffer.surfaces.http.app import create_app
    from coffer.surfaces.http.auth import set_active_token

    migrate(legacy.home, upgrade_db=UPGRADE, build="test")
    app = create_app()
    set_active_token(_TOKEN)
    headers = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}
    with TestClient(app, base_url="http://localhost", headers=headers) as client:
        for _id, kind, name, _config, enabled, agents, title in resources(legacy.home):
            got = client.get(f"/api/v1/resources/{UIDS[name]}")
            assert got.status_code == 200, (name, got.text)
            body = got.json()
            assert (body["kind"], body["name"], body["title"]) == (kind, name, title)
            if kind not in ("knowledge", "memory"):
                assert body["enabled"] is enabled, name
            if agents is not None and kind in ("mcp_server", "skill", "provider"):
                assert body["scope"]["agents"] == agents, name
        refs = client.get("/api/v1/secrets").json()["refs"]
        stored = {r["ref"] for r in refs if r["present"]}
        assert set(legacy.secrets) - {"proxy-token/claude_code"} <= stored


def test_the_daemon_refuses_a_home_that_still_holds_only_coffer_db(legacy: LegacyHome) -> None:
    with pytest.raises(MigrationRequired, match="coffer migrate"):
        run_migrations(f"sqlite+aiosqlite:///{legacy.coffer / 'runs.db'}")
    assert not (legacy.coffer / "runs.db").exists()
    assert not (legacy.coffer / "vault" / ".git").exists()


def _noop(*_a: Any, **_k: Any) -> None:
    return None


def test_the_upgrades_storage_rule_is_the_kinds_own() -> None:
    """The upgrade cannot build the kinds (they need the daemon's services),
    so it restates their storage rule; this holds the two together."""
    kinds: list[Kind] = [
        make_agent_kind(),
        make_channel_kind(),
        make_knowledge_kind(cast(Any, None)),
        make_mcp_kind({}),
        make_memory_kind(cast(Any, None)),
        make_provider_kind(),
        make_skill_kind(cast(Any, _noop)),
    ]
    configs = [{}, {"source": {"type": "builtin"}}, {"source": {"type": "local_import"}}]
    for kind in kinds:
        for config in configs:
            own = kind.storage_row(dict(config)) if kind.storage_row else kind.storage
            assert storage_of(kind.name, config) is own, (kind.name, config)

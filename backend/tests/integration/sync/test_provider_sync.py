"""Provider profiles round-trip through sync export/import (spec 011).

A ``provider`` resource rides the generic ResourceDoc machinery, so it converges
with no sync-engine changes. This exercises export → import across two vaults
sharing one workspace directory (no git layer needed for the round-trip proof).
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.provider.kind import make_provider_kind
from coffer.application.resource_service import ResourceService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.importer import SyncImporter
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
from coffer.infrastructure.sync.workspace import Workspace


class _NoKeyring:
    def get(self, ref: str) -> str | None:
        return None

    def set(self, ref: str, value: str) -> None:  # pragma: no cover - unused
        raise AssertionError("keychain not used")

    def delete(self, ref: str) -> None:  # pragma: no cover - unused
        pass


async def _vault(root: pathlib.Path) -> tuple[ResourceService, CredentialSyncAdapter]:
    root.mkdir(parents=True, exist_ok=True)
    db = root / "coffer.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds={"provider": make_provider_kind()},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    master_key = MasterKeyManager(root / "master.key", _NoKeyring())
    master_key.resolve(allow_create=True)
    return resources, CredentialSyncAdapter(db, master_key)


@pytest.mark.acceptance(
    spec="011-provider-switching",
    scenario="a provider profile round-trips through sync export and import",
)
async def test_provider_round_trips_through_sync(tmp_path):
    ws = tmp_path / "ws"
    config = {
        "wire_format": "openai",
        "base_url": "https://gw/v1",
        "credential_ref": "provider/acme/key",
        "model": "gpt-x",
        "fast_model": None,
        "wire_api": "chat",
        "is_active": True,
    }

    res_a, cred_a = await _vault(tmp_path / "A")
    await res_a.register("provider", "acme", config, "test")
    await SyncExporter(res_a, cred_a, Workspace(ws, trees=[])).export()

    res_b, cred_b = await _vault(tmp_path / "B")
    await SyncImporter(res_b, cred_b, Workspace(ws, trees=[])).import_()

    got = await res_b.get(ResourceRef("provider", "acme"))
    assert got.config == config

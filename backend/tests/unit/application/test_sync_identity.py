"""Unit tests for the machine-identity service (spec 010 amendment, ADR-043)."""

from __future__ import annotations

from typing import Any

from coffer.application.sync.identity import MachineIdentityService
from coffer.domain.sync.models import MachineIdentity


class _FakeRepo:
    def __init__(self) -> None:
        self.row: MachineIdentity | None = None
        self.creates = 0

    async def get(self) -> MachineIdentity | None:
        return self.row

    async def create(self, machine_id: str, display_name: str) -> MachineIdentity:
        self.creates += 1
        self.row = MachineIdentity(machine_id=machine_id, display_name=display_name)
        return self.row

    async def set_display_name(self, display_name: str) -> MachineIdentity:
        assert self.row is not None
        self.row = MachineIdentity(machine_id=self.row.machine_id, display_name=display_name)
        return self.row


class _FakeAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    async def record(self, event_type: str, *, actor: str, **_kw: Any) -> None:
        self.events.append((event_type, actor))


def _service(repo: _FakeRepo, audit: _FakeAudit, *, default_name: str = "host") -> Any:
    ids = iter(["01AAAAAAAAAAAAAAAAAAAAAAAA", "01BBBBBBBBBBBBBBBBBBBBBBBB"])
    return MachineIdentityService(
        repo,  # type: ignore[arg-type]
        audit,  # type: ignore[arg-type]
        new_id=lambda: next(ids),
        default_name=lambda: default_name,
    )


async def test_get_mints_once_and_stays_stable() -> None:
    repo, audit = _FakeRepo(), _FakeAudit()
    svc = _service(repo, audit)
    first = await svc.get()
    second = await svc.get()
    assert first == second
    assert first.machine_id == "01AAAAAAAAAAAAAAAAAAAAAAAA"
    assert first.display_name == "host"
    assert repo.creates == 1


async def test_blank_hostname_falls_back() -> None:
    repo, audit = _FakeRepo(), _FakeAudit()
    svc = _service(repo, audit, default_name="  ")
    identity = await svc.get()
    assert identity.display_name == "coffer"


async def test_rename_keeps_id_and_audits() -> None:
    repo, audit = _FakeRepo(), _FakeAudit()
    svc = _service(repo, audit)
    minted = await svc.get()
    renamed = await svc.rename("studio", actor="test")
    assert renamed.machine_id == minted.machine_id
    assert renamed.display_name == "studio"
    assert ("sync_machine_renamed", "test") in audit.events


async def test_rename_before_get_mints_first() -> None:
    repo, audit = _FakeRepo(), _FakeAudit()
    svc = _service(repo, audit)
    renamed = await svc.rename("studio", actor="test")
    assert renamed.display_name == "studio"
    assert repo.creates == 1

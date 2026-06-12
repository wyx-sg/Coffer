"""One-time migration of legacy OS-keychain secrets into the encrypted store."""

from __future__ import annotations

from typing import Any

from coffer.application.credential_migration import migrate_legacy_keychain
from coffer.domain.errors import CredentialLocked


class _FakeStore:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self.store.get(ref)

    def set(self, ref: str, value: str) -> None:
        self.store[ref] = value

    def delete(self, ref: str) -> None:
        self.store.pop(ref, None)


class _LockedKeyring(_FakeStore):
    def get(self, ref: str) -> str | None:
        raise CredentialLocked("locked")


class _FakeAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def record(self, event_type: str, **kw: Any) -> None:
        self.events.append((event_type, kw.get("details") or {}))


class _Resource:
    def __init__(self, kind: str, config: dict[str, Any]) -> None:
        self.kind = kind
        self.config = config


class _FakeRepo:
    def __init__(self, resources: list[_Resource]) -> None:
        self._resources = resources

    async def list(self, **_: Any) -> list[_Resource]:
        return list(self._resources)


class _Kind:
    def __init__(self, extractor: Any) -> None:
        self.credential_ref_extractor = extractor


def _mcp_kinds() -> dict[str, Any]:
    return {
        "mcp_server": _Kind(lambda cfg: dict(cfg.get("transport", {}).get("credential_refs", {}))),
        "agent": _Kind(None),
    }


async def test_moves_legacy_secret_and_audits() -> None:
    legacy, store, audit = _FakeStore(), _FakeStore(), _FakeAudit()
    legacy.store["gh-token"] = "s3cret"
    repo = _FakeRepo(
        [_Resource("mcp_server", {"transport": {"credential_refs": {"GH": "gh-token"}}})]
    )
    moved = await migrate_legacy_keychain(_mcp_kinds(), repo, legacy, store, audit)
    assert moved == 1
    assert store.store == {"gh-token": "s3cret"}
    assert legacy.store == {}
    assert audit.events == [("credential_migrated", {"ref": "gh-token"})]


async def test_skips_refs_already_in_store() -> None:
    legacy, store, audit = _FakeStore(), _FakeStore(), _FakeAudit()
    legacy.store["gh-token"] = "stale"
    store.store["gh-token"] = "current"
    repo = _FakeRepo(
        [_Resource("mcp_server", {"transport": {"credential_refs": {"GH": "gh-token"}}})]
    )
    assert await migrate_legacy_keychain(_mcp_kinds(), repo, legacy, store, audit) == 0
    assert store.store["gh-token"] == "current"
    assert legacy.store["gh-token"] == "stale"  # untouched — never overwrite


async def test_locked_keychain_skips_quietly() -> None:
    store, audit = _FakeStore(), _FakeAudit()
    repo = _FakeRepo(
        [_Resource("mcp_server", {"transport": {"credential_refs": {"GH": "gh-token"}}})]
    )
    assert await migrate_legacy_keychain(_mcp_kinds(), repo, _LockedKeyring(), store, audit) == 0
    assert store.store == {}


async def test_kinds_without_extractor_are_ignored() -> None:
    legacy, store, audit = _FakeStore(), _FakeStore(), _FakeAudit()
    repo = _FakeRepo([_Resource("agent", {"anything": True})])
    assert await migrate_legacy_keychain(_mcp_kinds(), repo, legacy, store, audit) == 0

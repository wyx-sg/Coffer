"""A round is recorded whatever locked-ref detection runs into.

Asking which refs are locked happens after the apply, so a failure there that
escaped the round would leave applied changes with no recorded run. And a key
that cannot be read (a locked keychain) says nothing about which refs are
locked, so the round names none rather than every one — while a machine that
genuinely holds no key names every ref it holds ciphertext for (spec vault-sync
"Report refs without a key as locked").
"""

from __future__ import annotations

import pathlib
import sqlite3

import pytest

from coffer.domain.credential_errors import CredentialLocked
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.sync.credentials import ResolvedMasterKey
from tests.integration.sync.harness import settle, two_machines

pytestmark = pytest.mark.timeout(120)


class _EmptyKeychain:
    """A keychain that answers, and holds no key."""

    def get(self, ref: str) -> str | None:
        return None

    def set(self, ref: str, value: str) -> None:  # pragma: no cover - unused
        raise AssertionError("unused")

    def delete(self, ref: str) -> None:  # pragma: no cover - unused
        raise AssertionError("unused")


class _LockedKeychain:
    def get(self, ref: str) -> str | None:
        raise CredentialLocked("keychain is locked")

    def set(self, ref: str, value: str) -> None:  # pragma: no cover - unused
        raise AssertionError("unused")

    def delete(self, ref: str) -> None:  # pragma: no cover - unused
        raise AssertionError("unused")


@pytest.fixture
async def pair(tmp_path: pathlib.Path):
    a, b = await two_machines(tmp_path)
    yield a, b
    await a.close()
    await b.close()


async def _deliver_ciphertext(a, b):  # type: ignore[no-untyped-def]
    a.set_credential("mcp/files/token", "s3cret-value")
    await a.register("mcp_server", "files", {"value": "f", "credential_ref": "mcp/files/token"})
    await settle(a)
    await b.remote_config()
    return b.service()


async def test_a_failing_locked_ref_check_still_records_the_round(pair, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    a, b = pair
    service = await _deliver_ciphertext(a, b)

    def busy() -> list[str]:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(b.credentials, "locked_refs", busy)
    run = await service.run_once(adopt=True)

    assert run.ok, run.error
    assert "credentials/mcp/files/token.enc" in {c.path for c in run.applied.changes}
    assert run.locked_refs == ()
    recorded = await service.last_run()
    assert recorded is not None
    assert recorded.commit == run.commit
    assert recorded.locked_refs == ()


@pytest.mark.acceptance(spec="vault-sync", scenario="an unreadable key reports no ref locked")
async def test_an_unreadable_key_reports_no_ref_locked_and_records_the_round(
    pair, tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    a, b = pair
    service = await _deliver_ciphertext(a, b)
    unreadable = ResolvedMasterKey(MasterKeyManager(tmp_path / "none" / "k", _LockedKeychain()))
    monkeypatch.setattr(b.credentials, "_master_key", unreadable)

    run = await service.run_once(adopt=True)

    assert run.ok, run.error
    assert run.locked_refs == ()
    recorded = await service.last_run()
    assert recorded is not None
    assert recorded.commit == run.commit


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a machine with no master key reports every ref it holds as locked",
)
async def test_a_machine_with_no_key_reports_every_ref_locked(pair, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    a, b = pair
    service = await _deliver_ciphertext(a, b)
    keyless = ResolvedMasterKey(MasterKeyManager(tmp_path / "none" / "k", _EmptyKeychain()))
    monkeypatch.setattr(b.credentials, "_master_key", keyless)

    run = await service.run_once(adopt=True)

    assert run.ok, run.error
    assert "mcp/files/token" in run.locked_refs
    assert set(run.locked_refs) == set(b.credentials.list_refs())
    recorded = await service.last_run()
    assert recorded is not None
    assert recorded.locked_refs == run.locked_refs

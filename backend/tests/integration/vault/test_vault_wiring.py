"""Finding a person's edits, wired as the lifespan runs it
(coffer.surfaces.http.vault_wiring; ADR
every-vault-write-is-a-validated-commit-naming-its-writer).

A hand edit is committed as a ``disk`` write and audited as
``vault_file_edited`` by ``human``; an invalid one stays out of ``HEAD``, is on
the problems list and the attention list, and the resource keeps its last
valid configuration. Every test runs in its own HOME (tests/conftest.py).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.resource import Kind
from coffer.domain.vault.findings import FindingCode
from coffer.domain.vault.writers import WRITER_DISK, WRITER_USER, CommitMeta
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.vault import git
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_repository, vault_writer
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.vault_routes import router as vault_router
from coffer.surfaces.http.vault_wiring import HUMAN, VaultScanning, start_vault_scanning
from tests.support.vault_stores import make_resource_repo

TOKEN = "t-vault-wiring"


class _Audit:
    def __init__(self, *, fail: bool = False) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []
        self._fail = fail

    async def record(
        self, event_type: str, *, actor: str = "system", details: dict[str, Any] | None = None
    ) -> None:
        if self._fail:
            raise RuntimeError("the audit store is down")
        self.events.append((event_type, actor, details or {}))


class WidgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    colour: str


class _NullAuditRepo:
    async def insert(self, entry: object) -> None:
        return None

    async def query(self, **_: object) -> list[object]:
        return []

    async def count(self, **_: object) -> int:
        return 0


async def _start(audit: _Audit) -> VaultScanning:
    return await start_vault_scanning(audit, watch=False, quiet=0.0, run=False)


async def _settle(scanning: VaultScanning) -> Any:
    """Two looks a quiet period (zero here) apart: the first records, the
    second settles."""
    await asyncio.to_thread(scanning.scanner.tick)
    result = await asyncio.to_thread(scanning.scanner.tick)
    await scanning.drain()
    return result


async def test_a_hand_edit_is_committed_as_disk_and_audited_as_human() -> None:
    audit = _Audit()
    scanning = await _start(audit)
    try:
        path = vault_root() / "knowledge" / "notes" / "a.md"
        path.parent.mkdir(parents=True)
        path.write_text("typed in an editor\n")
        result = await _settle(scanning)
        assert result is not None and result.meta.writer == WRITER_DISK
        assert vault_repository().read("HEAD", "knowledge/notes/a.md") == b"typed in an editor\n"
        assert audit.events == [
            (
                "vault_file_edited",
                HUMAN,
                {"path": "knowledge/notes/a.md", "version": result.version},
            )
        ]
    finally:
        await scanning.stop()


async def test_the_boot_scan_commits_edits_made_while_the_daemon_was_down() -> None:
    vault_repository().ensure()
    path = vault_root() / "knowledge" / "down.md"
    path.parent.mkdir(parents=True)
    path.write_text("edited while the daemon was down\n")
    audit = _Audit()
    scanning = await _start(audit)
    try:
        await scanning.drain()
        assert vault_writer().pending() == {}
        assert vault_repository().log(limit=1)[0].meta.writer == WRITER_DISK
        assert [e[2]["path"] for e in audit.events] == ["knowledge/down.md"]
    finally:
        await scanning.stop()


async def test_a_coffer_write_is_not_audited_as_a_hand_edit() -> None:
    audit = _Audit()
    scanning = await _start(audit)
    try:
        meta = CommitMeta(writer=WRITER_USER, operation="edit", summary="Saved", actor="ui")
        await asyncio.to_thread(
            vault_writer().write_file, "knowledge/b.md", b"b\n", meta=meta, expected=Expect.ABSENT
        )
        await scanning.drain()
        assert audit.events == []
    finally:
        await scanning.stop()


async def test_a_failed_audit_write_leaves_the_commit_standing() -> None:
    scanning = await _start(_Audit(fail=True))
    try:
        path = vault_root() / "knowledge" / "c.md"
        path.parent.mkdir(parents=True)
        path.write_text("c\n")
        result = await _settle(scanning)
        assert result is not None
        assert vault_repository().read("HEAD", "knowledge/c.md") == b"c\n"
    finally:
        await scanning.stop()


@pytest.mark.acceptance(
    spec="vault-storage", scenario="an invalid hand edit stays out of HEAD and is flagged"
)
@pytest.mark.acceptance(
    spec="vault-storage", scenario="refused hand edits are listed on REST and the command line"
)
async def test_an_invalid_resource_hand_edit_stays_out_of_head_and_is_flagged() -> None:
    kinds = {"widget": Kind(name="widget", display_name="Widget", config_schema=WidgetConfig)}
    svc = ResourceService(
        kinds=kinds, repo=make_resource_repo(kinds), audit=AuditService(_NullAuditRepo())
    )
    widget = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    before = vault_repository().read("HEAD", "resources/widget/w.json")
    (vault_root() / "resources" / "widget" / "w.json").write_text("{ not json")

    audit = _Audit()
    scanning = await _start(audit)  # the boot scan looks at it
    try:
        assert vault_repository().read("HEAD", "resources/widget/w.json") == before
        assert (await svc.get(widget.uid)).config["colour"] == "blue"
        assert audit.events == []

        items = await scanning.attention.items()
        assert [(i.title, i.reason_code) for i in items] == [
            ("resources/widget/w.json", f"vault_{FindingCode.INVALID_DOCUMENT.value}")
        ]

        set_active_token(TOKEN)
        app = FastAPI()
        err_handlers.register(app)
        app.include_router(vault_router)
        app.dependency_overrides[get_audit_service] = lambda: audit
        app.dependency_overrides[get_actor] = lambda: "ui"
        async with AsyncClient(
            transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": TOKEN}
        ) as client:
            r = await client.get("/api/v1/vault/problems")
        assert r.status_code == 200, r.text
        (problem,) = r.json()["problems"]
        assert problem["path"] == "resources/widget/w.json"
        assert problem["code"] == "invalid_document"
        assert problem["severity"] == "error"
    finally:
        await scanning.stop()


async def test_a_missing_git_is_a_startup_error_saying_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(git, "git_available", lambda: False)
    # A vault root no writer has ensured yet in this process.
    monkeypatch.setenv("HOME", str(vault_root().parent.parent / f"elsewhere-{uuid.uuid4().hex}"))
    with pytest.raises(RuntimeError, match="git is not installed"):
        await _start(_Audit())


@pytest.mark.acceptance(
    spec="vault-storage", scenario="a secret written before the first sync round is committed"
)
async def test_a_remote_that_carries_secrets_is_known_before_the_vault_opens() -> None:
    """``secret/`` is committed from the first write after a restart when the
    stored remote carries secrets, not only once a sync round has run."""
    import json

    from coffer.infrastructure.vault.home import local_root
    from coffer.surfaces.http import vault_composition

    remote_json = local_root() / "sync" / "remote.json"
    remote_json.parent.mkdir(parents=True, exist_ok=True)
    remote_json.write_text(
        json.dumps({"url": "https://example.invalid/vault.git", "include_secret": True})
    )
    vault_repository().set_carry_secret(False)  # a fresh process starts here
    stores = await vault_composition.build_vault_stores({})
    try:
        assert vault_repository().carries_secret is True
        exclude = (vault_root() / ".git" / "info" / "exclude").read_text()
        assert "/secret/" not in exclude
    finally:
        await stores.derived_engine.dispose()

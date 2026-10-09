"""What the stores do with a commit they did not make, and with a path the
writer holds (spec vault-storage "Keep the last valid version when a hand edit
is invalid"; the resource-framework hint seam).

A hand edit the scanner settles, a sync round's checkout, a restore: each
reaches the vault writer's listeners, and each must refresh the stores and
reach the reconciler and the event stream as a ``Changed`` hint exactly like an
API write. A path the writer holds (a join's differing file left as it is here)
is in effect from disk, not from ``HEAD``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.reconcile import Changed
from coffer.domain.resource import Kind
from coffer.domain.vault.writers import OP_UPDATE, WRITER_SYNC, CommitMeta
from coffer.domain.vault.writes import CommitResult
from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceStore
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_repository, vault_writer
from coffer.infrastructure.vault.resource_store import FileResourceRepo
from tests.support.vault_stores import derived_db, make_resource_repo


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    colour: str = ""


class _NullAudit:
    async def insert(self, entry: object) -> None:
        return None


def _kinds() -> dict[str, Kind]:
    return {
        "widget": Kind(name="widget", display_name="Widget", config_schema=_Config),
        "mcp_server": Kind(name="mcp_server", display_name="MCP", config_schema=_Config),
    }


def _setup() -> tuple[ResourceService, FileResourceRepo, list[Changed]]:
    kinds = _kinds()
    repo = make_resource_repo(kinds)
    svc = ResourceService(kinds=kinds, repo=repo, audit=AuditService(_NullAudit()))  # type: ignore[arg-type]
    hints: list[Changed] = []
    repo.set_change_sink(hints.append)
    return svc, repo, hints


def _file(path: str) -> Path:
    return vault_root() / path


def _recolour(path: str, colour: str) -> None:
    doc = json.loads(_file(path).read_text())
    doc["config"]["colour"] = colour
    _file(path).write_text(json.dumps(doc, indent=2) + "\n")


async def test_the_stores_own_writes_are_not_hinted_twice() -> None:
    svc, _repo, hints = _setup()
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    await svc.update_config(r.uid, {"colour": "red"}, actor="user")
    await svc.rename(r.uid, "w2", actor="user")
    # The hinting wrapper announces these; the store's listener stays quiet.
    assert hints == []


@pytest.mark.acceptance(
    spec="vault-storage", scenario="a hand edit reaches the reconciler like an API write"
)
async def test_a_settled_hand_edit_is_hinted_like_an_api_write() -> None:
    svc, repo, hints = _setup()
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    _recolour("resources/widget/w.json", "red")
    vault_writer().settle()
    found = await repo.find(r.uid)
    assert found is not None and found.config["colour"] == "red"
    assert hints == [Changed("widget", r.uid, "upsert")]


async def test_a_file_removed_by_hand_is_hinted_as_a_delete() -> None:
    svc, repo, hints = _setup()
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    _file("resources/widget/w.json").unlink()
    vault_writer().settle()
    assert await repo.find(r.uid) is None
    assert hints == [Changed("widget", r.uid, "delete")]


async def test_a_commit_from_another_thread_reaches_the_loop() -> None:
    """A sync round or the scanner commits in a worker thread; the hint is
    handed to the event loop, never called on the worker."""
    svc, _repo, hints = _setup()
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    _recolour("resources/widget/w.json", "green")
    await asyncio.to_thread(vault_writer().settle)
    await asyncio.sleep(0)
    assert [(h.uid, h.op) for h in hints] == [(r.uid, "upsert")]


@pytest.mark.acceptance(spec="vault-storage", scenario="a held file is in effect from disk")
async def test_a_held_path_is_in_effect_from_disk() -> None:
    svc, repo, hints = _setup()
    r = await svc.register("widget", "w", {"colour": "blue"}, actor="user")
    path = "resources/widget/w.json"
    head = vault_repository().head()
    assert head is not None
    # A join's "take the other version": the bytes land on disk, HEAD does
    # not move, and the writer holds the path until the person chooses.
    vault_writer().set_held(lambda: [path])
    _recolour(path, "red")
    vault_writer().notify(
        CommitResult(
            head, CommitMeta(writer=WRITER_SYNC, operation=OP_UPDATE, summary="x"), (path,)
        )
    )
    found = await repo.find(r.uid)
    assert found is not None and found.config["colour"] == "red"
    assert [(h.uid, h.op) for h in hints] == [(r.uid, "upsert")]
    # A full re-read keeps the held file's version, and it is never settled.
    repo.invalidate()
    again = await repo.find(r.uid)
    assert again is not None and again.config["colour"] == "red"
    assert path not in vault_writer().pending()
    assert json.loads(vault_repository().read("HEAD", path) or b"{}")["config"]["colour"] == "blue"


async def test_a_state_document_changed_by_hand_hints_its_owner() -> None:
    svc, repo, hints = _setup()
    server = await svc.register("mcp_server", "gh", {}, actor="user")
    async with derived_db() as sm:
        prefs = MCPCapabilityPreferenceStore(sm, name_of=repo.name_of)
        prefs.documents.add_owner_listener(repo.announce)
        prefs.documents.put(server.uid, "gh", {"disabled": {"tool": ["x"]}}, summary="t")
        hints.clear()
        path = "state/mcp-preferences/gh.json"
        doc = json.loads(_file(path).read_text())
        doc["disabled"] = {"tool": ["y"]}
        _file(path).write_text(json.dumps(doc, indent=2) + "\n")
        vault_writer().settle()
        off = {p.capability_key for p in await prefs.list_for(server.uid) if not p.enabled}
        assert off == {"y"}
        assert [(h.kind, h.uid, h.op) for h in hints] == [("mcp_server", server.uid, "upsert")]


async def test_a_held_state_document_is_read_from_disk() -> None:
    svc, repo, _hints = _setup()
    server = await svc.register("mcp_server", "gh", {}, actor="user")
    async with derived_db() as sm:
        prefs = MCPCapabilityPreferenceStore(sm, name_of=repo.name_of)
        prefs.documents.put(server.uid, "gh", {"disabled": {"tool": ["x"]}}, summary="t")
        path = "state/mcp-preferences/gh.json"
        vault_writer().set_held(lambda: [path])
        doc = json.loads(_file(path).read_text())
        doc["disabled"] = {"tool": ["y"]}
        _file(path).write_text(json.dumps(doc, indent=2) + "\n")
        prefs.documents.invalidate()
        off = {p.capability_key for p in await prefs.list_for(server.uid) if not p.enabled}
        assert off == {"y"}

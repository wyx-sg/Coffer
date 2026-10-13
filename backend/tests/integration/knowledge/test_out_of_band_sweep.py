"""The sweep does the mechanical upkeep of a collection with no model and no button.

Real git over a real directory, because "found on disk" is decided by what the
vault repository has committed. The registry and the audit log are in-memory
stand-ins. Each tick promotes what waits in an inbox, commits edits found on
disk, and re-renders the guide; it never moves a file (spec
knowledge "Adopt a file dropped into the inbox", "Sweep the knowledge root on
its mechanical duties", "Treat a direct file edit as a complete change").
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import time
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.knowledge.sweep import sweep_once
from coffer.domain.resource import Resource
from coffer.domain.vault.writers import CommitMeta
from coffer.infrastructure.knowledge import fs, inbox, paths
from coffer.infrastructure.knowledge.history import KnowledgeHistory
from coffer.infrastructure.vault.instance import vault_writer

pytestmark = pytest.mark.anyio

_DROPPED = "The account gateway owns the session cache.\n"


class _Resources:
    def __init__(self, names: list[str]) -> None:
        now = datetime.now(tz=UTC)
        self.rows = [
            Resource(
                uid=f"uid-{i}",
                kind=KIND_KNOWLEDGE,
                name=name,
                description=None,
                config={},
                enabled=True,
                created_at=now,
                updated_at=now,
                scope=None,
            )
            for i, name in enumerate(names, start=1)
        ]

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> list[Resource]:
        return list(self.rows)


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def record(self, event_type: str, **kwargs: Any) -> None:
        self.events.append((event_type, dict(kwargs.get("details") or {})))


class _Guide:
    def __init__(self) -> None:
        self.refreshes = 0

    async def refresh(self) -> bool:
        self.refreshes += 1
        return False


def _world() -> tuple[KnowledgeService, KnowledgeHistory, _Audit]:
    fs.create_collection_dir("shopee")
    history = KnowledgeHistory()
    assert history.available()
    audit = _Audit()
    service = KnowledgeService(
        resources=_Resources(["shopee"]),  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        history=history,
    )
    return service, history, audit


def _drop_inbox(name: str, text: str) -> None:
    directory = paths.inbox_dir("shopee")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


@pytest.mark.acceptance(spec="knowledge", scenario="a sweep promotes a file dropped into the inbox")
async def test_a_file_dropped_into_the_inbox_becomes_a_document_on_the_next_sweep() -> None:
    service, _, audit = _world()
    guide = _Guide()
    _drop_inbox("gateway.md", f"# Gateway\n\n{_DROPPED}")

    await sweep_once(service, guide.refresh)

    assert inbox.inbox_items("shopee") == ()
    document = fs.read_file("shopee/sources/gateway.md")
    assert document.title == "Gateway"
    assert document.description == _DROPPED.strip()
    assert document.actor == "agent"
    assert [t for t, _ in audit.events] == ["knowledge_written"]
    assert guide.refreshes == 1


async def test_a_second_sweep_finds_nothing_to_do() -> None:
    service, history, _ = _world()
    guide = _Guide()
    _drop_inbox("gateway.md", f"# Gateway\n\n{_DROPPED}")

    await sweep_once(service, guide.refresh)
    commits = len(history.log("shopee"))
    await sweep_once(service, guide.refresh)

    assert len(history.log("shopee")) == commits


@pytest.mark.acceptance(spec="knowledge", scenario="a sweep catalogues a document added by hand")
async def test_a_document_dropped_in_by_hand_is_committed_as_a_disk_write() -> None:
    service, history, _ = _world()
    guide = _Guide()
    paths.pages_dir("shopee").mkdir(parents=True)
    (paths.pages_dir("shopee") / "by-hand.md").write_text(_DROPPED, encoding="utf-8")

    await sweep_once(service, guide.refresh)
    assert guide.refreshes == 1

    [change] = history.log("shopee", limit=1)
    assert change.meta.writer == "disk"
    assert [d.path for d in change.documents] == ["shopee/pages/by-hand.md"]


async def test_a_failing_guide_refresh_does_not_stop_the_sweep() -> None:
    service, _, _ = _world()
    _drop_inbox("gateway.md", f"# Gateway\n\n{_DROPPED}")

    async def broken() -> bool:
        raise RuntimeError("render failed")

    await sweep_once(service, broken)

    assert inbox.inbox_items("shopee") == ()


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="an agent's new document is live at once and committed as a disk edit",
)
async def test_an_agents_new_document_is_readable_before_any_sweep() -> None:
    service, history, _ = _world()
    paths.pages_dir("shopee").mkdir(parents=True)
    (paths.pages_dir("shopee") / "agent.md").write_text(
        f"---\ntitle: Agent\ndescription: d\nactor: agent\n---\n\n{_DROPPED}",
        encoding="utf-8",
    )

    assert _DROPPED.strip() in fs.read_file("shopee/pages/agent.md").body

    await sweep_once(service, _Guide().refresh)

    [change] = history.log("shopee", limit=1)
    assert change.meta.writer == "disk"
    assert [d.path for d in change.documents] == ["shopee/pages/agent.md"]


def _age(path: pathlib.Path, seconds: float = 120) -> None:
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


@pytest.mark.acceptance(
    spec="knowledge", scenario="a sweep leaves every file where its writer put it"
)
async def test_sweeps_leave_root_files_and_custom_folders_in_place() -> None:
    service, history, _ = _world()
    guide = _Guide()
    root = paths.collection_dir("shopee")
    files = {
        "README.md": "# shopee\n\nThe schema.\n",
        "index.md": "# Index\n\n- [Gateway](pages/gateway.md)\n",
        "log.md": "# Log\n\n- 2026-10-13 added the gateway page\n",
        "schema.md": "# Schema\n\nPages carry a subject_kind.\n",
        "glossary.md": "# Glossary\n\nA root file of the person's own.\n",
        "services/notes.md": "---\ntitle: Notes\n---\n\nIn a folder of their own.\n",
        "pages/gateway.md": "---\ntitle: Gateway\ntype: entity\n---\n\nSee [index](../index.md).\n",
        "assets/gateway/diagram.drawio": "<mxfile/>\n",
    }
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        _age(target)

    for _ in range(3):
        await sweep_once(service, guide.refresh)

    for relative, text in files.items():
        assert (root / relative).read_text(encoding="utf-8") == text, relative
    assert not (root / "pages" / "index.md").exists()
    assert all(c.meta.operation != "layout" for c in history.log("shopee"))
    committed = {d.path for c in history.log("shopee") for d in c.documents}
    assert {"shopee/index.md", "shopee/log.md", "shopee/services/notes.md"} <= committed


@pytest.mark.acceptance(spec="knowledge", scenario="a sweep runs while a sync round waits")
async def test_a_sweep_does_not_wait_for_a_long_operation_holding_other_paths() -> None:
    service, _, _ = _world()
    _drop_inbox("gateway.md", f"# Gateway\n\n{_DROPPED}")
    # A sync round that waits for a person holds its paths open without the lock.
    held = vault_writer().begin(
        CommitMeta(writer="sync", operation="sync", summary="waiting", actor="sync")
    )
    held.touch("state/settings/waiting.json")
    try:
        await asyncio.wait_for(sweep_once(service, _Guide().refresh), timeout=10)
    finally:
        held.abort()

    assert inbox.inbox_items("shopee") == ()
    assert fs.read_file("shopee/sources/gateway.md").title == "Gateway"

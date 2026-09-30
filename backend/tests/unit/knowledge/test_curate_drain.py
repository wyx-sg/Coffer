"""Curate now drains a collection, one pass at a time (spec knowledge "Run
curation on a sweep and on demand").

The run is exercised with the real pass (``run_curation``) over a scripted
agentic loop, so what is asserted is the order items are taken in, the bound
each pass keeps, what is settled, and where a run stops — not a fake's idea of
them.
"""

from __future__ import annotations

import os
import time
from typing import Any

import pytest

from coffer.application.knowledge.curate import pending_items, run_curation
from coffer.application.knowledge.curate_drain import drain
from coffer.application.knowledge.curate_tools import MAX_WRITES_PER_PASS
from coffer.domain.knowledge.entry import Pending
from coffer.infrastructure.knowledge import fs, inbox

from .test_curation import _SHOPEE_UID, _Loop, _Model, _service


def _material(title: str) -> str:
    name = inbox.submit_material("shopee", title=title, description="d", body=title, actor="user")
    # Distinct modification times, so "oldest first" has an order to keep.
    stamp = time.time() - 100 + len(pending_items("shopee"))
    os.utime(inbox._inbox_item("shopee", name), (stamp, stamp))
    return name


def _edited(title: str) -> str:
    path = fs.write_file(
        directory="shopee", title=title, description="d", body="b", curated=True
    ).path
    # A person's edit on disk changes the content curation last settled.
    target = fs.paths.resolve(path)
    target.write_text(target.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")
    return path


class _Recording:
    """The pass, recording which item each call took and what it answered."""

    def __init__(self, fail_on: int | None = None) -> None:
        self.items: list[Pending | None] = []
        self._fail_on = fail_on

    async def __call__(self, service: Any, uid: str, *, item: Pending | None, actor: str) -> dict:
        self.items.append(item)
        if self._fail_on is not None and len(self.items) == self._fail_on:
            # What the real pass answers when its loop raised: the item stays.
            return {"status": "failed", "collection": "shopee", "item": str(item)}
        return await run_curation(
            service,
            uid,
            item=item,
            actor=actor,
            agent=_Loop([]),
            models=_Model(),
            credential_resolver=lambda ref: "key",
        )


@pytest.mark.acceptance(
    spec="knowledge", scenario="curate now drains a collection until nothing is pending"
)
@pytest.mark.anyio
async def test_curate_now_runs_a_pass_per_item_until_nothing_is_pending() -> None:
    first, second, third = _material("One"), _material("Two"), _material("Three")
    document = _edited("Edited by hand")
    curate = _Recording()

    run = await drain(curate, _service(), _SHOPEE_UID)

    # Four passes, one after another: the three items oldest first, then the
    # document edited out of band.
    assert curate.items == [
        Pending(material=first),
        Pending(material=second),
        Pending(material=third),
        Pending(document=document),
    ]
    assert run["status"] == "ok"
    assert run["total"] == 4
    assert [p["status"] for p in run["passes"]] == ["ok"] * 4
    # Each still within the eight-write bound.
    assert all(p["written"] + p["retired"] <= MAX_WRITES_PER_PASS for p in run["passes"])
    assert inbox.inbox_items("shopee") == ()
    assert pending_items("shopee") == ()


@pytest.mark.acceptance(spec="knowledge", scenario="curate now reports progress")
@pytest.mark.anyio
async def test_curate_now_reports_n_of_m_as_passes_finish() -> None:
    for title in ("One", "Two", "Three"):
        _material(title)
    seen: list[tuple[int, int]] = []

    async def progress(done: int, total: int) -> None:
        seen.append((done, total))

    await drain(_Recording(), _service(), _SHOPEE_UID, on_progress=progress)

    assert seen == [(0, 3), (1, 3), (2, 3), (3, 3)]


@pytest.mark.acceptance(spec="knowledge", scenario="curate now stops at the first failed pass")
@pytest.mark.anyio
async def test_curate_now_stops_at_the_first_failed_pass() -> None:
    first, second, third = _material("One"), _material("Two"), _material("Three")
    curate = _Recording(fail_on=2)

    run = await drain(curate, _service(), _SHOPEE_UID)

    assert run["status"] == "failed"
    assert [p["status"] for p in run["passes"]] == ["ok", "failed"]
    # The first item is settled; the second and third are still pending.
    assert inbox.inbox_items("shopee") == (second, third)
    assert first not in inbox.inbox_items("shopee")


@pytest.mark.acceptance(spec="knowledge", scenario="curate now on one document curates only it")
@pytest.mark.anyio
async def test_curate_now_on_one_document_curates_only_it() -> None:
    first, second = _material("One"), _material("Two")
    document = _edited("The one I mean")
    curate = _Recording()

    run = await drain(curate, _service(), _SHOPEE_UID, document=document)

    assert curate.items == [Pending(document=document)]
    assert run["total"] == 1
    assert inbox.inbox_items("shopee") == (first, second)


@pytest.mark.anyio
async def test_curate_now_with_nothing_pending_is_up_to_date() -> None:
    run = await drain(_Recording(), _service(), _SHOPEE_UID)

    assert run["status"] == "up_to_date"
    assert run["total"] == 0


@pytest.mark.anyio
async def test_an_item_settled_meanwhile_is_skipped_but_counted() -> None:
    first, second = _material("One"), _material("Two")
    seen: list[tuple[int, int]] = []

    async def progress(done: int, total: int) -> None:
        seen.append((done, total))
        if done == 1:
            # Someone else settled the second item while the first pass ran.
            inbox.discard_material("shopee", second)

    curate = _Recording()
    run = await drain(curate, _service(), _SHOPEE_UID, on_progress=progress)

    assert curate.items == [Pending(material=first)]
    assert seen[-1] == (2, 2)
    assert run["status"] == "ok"

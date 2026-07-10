"""Memory store labels as a synced state area (spec 010 x spec 007 FR-017c)."""

from __future__ import annotations

import subprocess

import pytest
import pytest_asyncio

from coffer.application.memory.labels_sync import MemoryLabelsSyncState
from coffer.infrastructure.memory.store_label_repo import StoreLabelRepo

from .test_two_machine_sync import _make_machine


@pytest_asyncio.fixture
async def remote(tmp_path):  # type: ignore[no-untyped-def]
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    return bare


def _providers(resources, sm):  # type: ignore[no-untyped-def]
    return (MemoryLabelsSyncState(StoreLabelRepo(sm)),)


@pytest.mark.acceptance(spec="010-sync", scenario="only shared state syncs")
async def test_labels_round_trip_and_rename(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine(
        "A", tmp_path / "A", remote, create_key=True, state_providers_factory=_providers
    )
    labels_a = StoreLabelRepo(a.sm)
    await labels_a.set("project-01ULIDULIDULIDULIDULIDUL", "工作台后端")
    await a.service.run()

    b = await _make_machine(
        "B", tmp_path / "B", remote, create_key=True, state_providers_factory=_providers
    )
    await b.service.run()

    # The label arrived: the ULID store reads by its name on B.
    labels_b = StoreLabelRepo(b.sm)
    assert await labels_b.get("project-01ULIDULIDULIDULIDULIDUL") == "工作台后端"

    # A rename on B propagates back to A (B owns the store once labelled).
    await labels_b.set("project-01ULIDULIDULIDULIDULIDUL", "wealthbutler")
    await b.service.run()
    await a.service.run()
    assert await labels_a.get("project-01ULIDULIDULIDULIDULIDUL") == "wealthbutler"


async def test_malformed_label_doc_is_skipped(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine(
        "A", tmp_path / "A", remote, create_key=True, state_providers_factory=_providers
    )
    area = tmp_path / "A" / "ws" / "state" / "memory-labels"
    area.mkdir(parents=True, exist_ok=True)
    (area / "project-x.yaml").write_text("label: ''\n", encoding="utf-8")
    (area / "project-y.yaml").write_text("nonsense: 1\n", encoding="utf-8")

    state = await a.service.run()

    # Malformed docs neither error the run nor create labels.
    assert not state.failed_state_paths
    assert await StoreLabelRepo(a.sm).list_all() == {}


async def test_clearing_a_label_propagates_and_never_resurrects(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """Review #292 finding 1: without a clear marker, the cleared label came
    back from the workspace's stale doc within ONE run. The clear must hold
    locally across runs AND propagate to the other machine."""
    store = "project-01ULIDULIDULIDULIDULIDUL"
    a = await _make_machine(
        "A", tmp_path / "A", remote, create_key=True, state_providers_factory=_providers
    )
    labels_a = StoreLabelRepo(a.sm)
    await labels_a.set(store, "工作台后端")
    await a.service.run()

    b = await _make_machine(
        "B", tmp_path / "B", remote, create_key=True, state_providers_factory=_providers
    )
    await b.service.run()
    labels_b = StoreLabelRepo(b.sm)
    assert await labels_b.get(store) == "工作台后端"

    # A clears; the label must stay cleared on A across its own run…
    await labels_a.clear(store)
    await a.service.run()
    assert await labels_a.get(store) is None

    # …and the clear reaches B (and holds there across another round).
    await b.service.run()
    assert await labels_b.get(store) is None
    await a.service.run()
    assert await labels_a.get(store) is None

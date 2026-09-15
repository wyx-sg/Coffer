"""Engine settings as a synced state area (spec vault-sync).

The area publishes a decision, not a row: the defaults write no document, a
deletion means "back to the defaults", and honouring one leaves nothing to
republish. These tests pin the three edges of that — a non-default choice is
published, a deletion resets it and the next export is empty, and a persisted
row that merely holds the defaults is as silent as no row at all.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.engine_settings_sync import AREA, DOC, EngineSettingsSyncState
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.domain.internal_engine_config import GlobalInternalEngineConfig


class _Repo:
    """The singleton row, in memory; ``None`` until something is persisted."""

    def __init__(self, row: GlobalInternalEngineConfig | None = None) -> None:
        self.row = row

    async def get(self) -> GlobalInternalEngineConfig | None:
        return self.row

    async def set(
        self,
        *,
        model: str | None,
        auto_tidy_enabled: bool | None = None,
        tidy_owner_machine_id: str | None = None,
    ) -> GlobalInternalEngineConfig:
        current = self.row or GlobalInternalEngineConfig(model=None, updated_at=_now())
        auto_tidy = current.auto_tidy_enabled if auto_tidy_enabled is None else auto_tidy_enabled
        owner = current.tidy_owner_machine_id
        if tidy_owner_machine_id is not None:
            owner = tidy_owner_machine_id or None
        self.row = GlobalInternalEngineConfig(
            model=model, updated_at=_now(), auto_tidy_enabled=auto_tidy, tidy_owner_machine_id=owner
        )
        return self.row


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    async def record(self, event_type: str, *, actor: str, details: object = None) -> None:
        self.events.append((event_type, actor))


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _state(row: GlobalInternalEngineConfig | None) -> tuple[EngineSettingsSyncState, _Repo, _Audit]:
    repo = _Repo(row)
    audit = _Audit()
    service = InternalEngineConfigService(repo=repo, audit=audit)  # type: ignore[arg-type]
    return EngineSettingsSyncState(service, internal_repo=repo), repo, audit


def _chosen() -> GlobalInternalEngineConfig:
    return GlobalInternalEngineConfig(
        model="agnes-2.0", updated_at=_now(), auto_tidy_enabled=True, tidy_owner_machine_id="m1"
    )


async def test_a_non_default_choice_is_published_as_the_one_doc() -> None:
    state, _repo, _audit = _state(_chosen())
    docs, owned = await state.export_docs()
    assert AREA == "settings"
    assert owned == [DOC]
    assert docs == [
        (DOC, {"model": "agnes-2.0", "auto_tidy_enabled": True, "tidy_owner_machine_id": "m1"})
    ]


async def test_deleting_the_doc_resets_to_defaults_and_publishes_nothing_after() -> None:
    state, repo, audit = _state(_chosen())

    await state.delete_docs([DOC])

    assert repo.row is not None
    assert repo.row.model is None
    assert repo.row.auto_tidy_enabled is False
    assert repo.row.tidy_owner_machine_id is None
    assert audit.events == [("internal_engine_model_set", "sync")]
    # The reset is not re-published as a fresh document: that is what stops a
    # machine that never persisted a row from deleting it again next round.
    assert await state.export_docs() == ([], [])


async def test_a_persisted_row_holding_the_defaults_publishes_nothing() -> None:
    state, _repo, _audit = _state(GlobalInternalEngineConfig(model=None, updated_at=_now()))
    assert await state.export_docs() == ([], [])


async def test_no_row_publishes_nothing() -> None:
    state, _repo, _audit = _state(None)
    assert await state.export_docs() == ([], [])


async def test_deleting_when_the_defaults_already_hold_writes_nothing() -> None:
    state, repo, audit = _state(None)
    await state.delete_docs([DOC])
    assert repo.row is None
    assert audit.events == []


async def test_an_unknown_rel_is_ignored() -> None:
    state, repo, audit = _state(_chosen())
    await state.delete_docs(["something-else"])
    assert repo.row is not None and repo.row.model == "agnes-2.0"
    assert audit.events == []


@pytest.mark.parametrize("path", [DOC, "other"])
async def test_import_applies_only_the_singleton_doc(path: str) -> None:
    state, repo, _audit = _state(None)
    errors = await state.import_docs(
        [(path, {"model": "agnes-1.5-flash", "auto_tidy_enabled": False})]
    )
    assert errors == []
    assert (repo.row is not None) is (path == DOC)

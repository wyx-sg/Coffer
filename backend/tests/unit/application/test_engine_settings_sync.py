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
from coffer.domain.internal_engine_config import (
    AGGREGATE,
    CURATE,
    DISTIL,
    GlobalInternalEngineConfig,
    UpkeepSetting,
)

#: What a document carries for a fleet that has changed nothing about upkeep.
_DEFAULT_UPKEEP = {
    AGGREGATE: {"enabled": True, "interval_s": None},
    DISTIL: {"enabled": True, "interval_s": None},
    CURATE: {"enabled": True, "interval_s": None},
}


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
        curate_owner_machine_id: str | None = None,
        upkeep: dict[str, UpkeepSetting] | None = None,
    ) -> GlobalInternalEngineConfig:
        current = self.row or GlobalInternalEngineConfig(model=None, updated_at=_now())
        auto_tidy = current.auto_curate_enabled
        owner = current.curate_owner_machine_id
        if curate_owner_machine_id is not None:
            owner = curate_owner_machine_id or None
        fields = {
            "auto_aggregate_enabled": current.auto_aggregate_enabled,
            "aggregate_interval_s": current.aggregate_interval_s,
            "auto_distil_enabled": current.auto_distil_enabled,
            "distil_interval_s": current.distil_interval_s,
            "curate_interval_s": current.curate_interval_s,
        }
        for name, setting in (upkeep or {}).items():
            if name == AGGREGATE:
                fields["auto_aggregate_enabled"] = setting.enabled
                fields["aggregate_interval_s"] = setting.interval_s
            elif name == DISTIL:
                fields["auto_distil_enabled"] = setting.enabled
                fields["distil_interval_s"] = setting.interval_s
            else:
                auto_tidy = setting.enabled
                fields["curate_interval_s"] = setting.interval_s
        self.row = GlobalInternalEngineConfig(
            model=model,
            updated_at=_now(),
            auto_curate_enabled=auto_tidy,
            curate_owner_machine_id=owner,
            **fields,
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
        model="agnes-2.0", updated_at=_now(), auto_curate_enabled=True, curate_owner_machine_id="m1"
    )


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="the engine's settings converge and a deletion means the defaults",
)
async def test_a_non_default_choice_is_published_as_the_one_doc() -> None:
    state, _repo, _audit = _state(_chosen())
    docs = await state.export_docs()
    assert AREA == "settings"
    assert docs == [
        (
            DOC,
            {
                "model": "agnes-2.0",
                "auto_curate_enabled": True,
                "curate_owner_machine_id": "m1",
                "upkeep": _DEFAULT_UPKEEP,
            },
        )
    ]


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="the engine's settings converge and a deletion means the defaults",
)
async def test_deleting_the_doc_resets_to_defaults_and_publishes_nothing_after() -> None:
    state, repo, audit = _state(_chosen())

    await state.delete_docs([DOC])

    assert repo.row is not None
    assert repo.row.model is None
    # The defaults, which is what "reset" means — and curation's default is ON
    # (spec internal-engine): it derives the documents agents read from sources
    # it never rewrites, so a vault where it never runs has an empty lane.
    assert repo.row.auto_curate_enabled is True
    assert repo.row.curate_owner_machine_id is None
    assert audit.events == [("internal_engine_model_set", "sync")]
    # The reset is not re-published as a fresh document: that is what stops a
    # machine that never persisted a row from deleting it again next round.
    assert await state.export_docs() == []


async def test_a_persisted_row_holding_the_defaults_publishes_nothing() -> None:
    state, _repo, _audit = _state(GlobalInternalEngineConfig(model=None, updated_at=_now()))
    assert await state.export_docs() == []


async def test_no_row_publishes_nothing() -> None:
    state, _repo, _audit = _state(None)
    assert await state.export_docs() == []


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
        [(path, {"model": "agnes-1.5-flash", "auto_curate_enabled": False})]
    )
    assert errors == []
    assert (repo.row is not None) is (path == DOC)


async def test_a_switched_off_rewriter_travels_to_the_other_machines() -> None:
    """Switching a rewriter off is exactly the decision a second machine must
    not be left out of — so it is part of the published document, not local."""
    row = GlobalInternalEngineConfig(
        model=None,
        updated_at=_now(),
        auto_aggregate_enabled=False,
        # Switched off explicitly: curation ships ON, so leaving it at its
        # default would make this test assert nothing about travelling.
        auto_curate_enabled=False,
        distil_interval_s=900,
    )
    state, _repo, _audit = _state(row)

    docs = await state.export_docs()

    assert docs[0][1]["upkeep"] == {
        AGGREGATE: {"enabled": False, "interval_s": None},
        DISTIL: {"enabled": True, "interval_s": 900},
        CURATE: {"enabled": False, "interval_s": None},
    }


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="the engine's settings converge and a deletion means the defaults",
)
async def test_upkeep_at_its_defaults_publishes_no_document() -> None:
    # The area publishes a DECISION: a row holding only the defaults says the
    # same thing as no row, and publishing it would be re-adding a document
    # every fresh machine deletes again.
    state, _repo, _audit = _state(GlobalInternalEngineConfig(model=None, updated_at=_now()))

    assert await state.export_docs() == []


async def test_a_document_written_before_upkeep_travelled_changes_nothing() -> None:
    """An older machine in the fleet is not a decision.

    Its document carries no upkeep block at all, and reading that as "the
    defaults" would silently switch a rewriter back on — or off — on every
    machine that is up to date.
    """
    row = GlobalInternalEngineConfig(
        model="agnes-2.0",
        updated_at=_now(),
        auto_aggregate_enabled=False,
        curate_interval_s=900,
    )
    state, repo, _audit = _state(row)

    errors = await state.import_docs([(DOC, {"model": "agnes-2.0"})])

    assert errors == []
    assert repo.row is not None
    assert repo.row.auto_aggregate_enabled is False
    assert repo.row.curate_interval_s == 900


async def test_an_imported_document_applies_its_upkeep() -> None:
    state, repo, _audit = _state(GlobalInternalEngineConfig(model=None, updated_at=_now()))

    errors = await state.import_docs(
        [(DOC, {"model": None, "upkeep": {DISTIL: {"enabled": False, "interval_s": 1800}}})]
    )

    assert errors == []
    assert repo.row is not None
    assert repo.row.auto_distil_enabled is False
    assert repo.row.distil_interval_s == 1800

"""Engine settings as a synced state area (spec vault-sync slice 7).

The internal-engine model choice is an installation-wide singleton that should
match across machines: Coffer's own passes behave the same everywhere only when
they run on the same model. What those passes are ALLOWED to do unattended, and
how often, travels with it — switching a rewriter off is exactly the decision a
second machine must not be left out of.

The area publishes a **decision, not a row**. A machine that never chose a
model and a machine whose choice was taken back say the same thing — "the
defaults" — and neither writes a document. That is what lets the singleton
converge under bidirectional sync: the tree holds ``internal-engine.yaml``
exactly while some machine holds a non-default choice, a deletion of it means
"back to the defaults", and honouring that deletion here leaves nothing to
republish. Had a machine re-published its defaults as a document, a fresh
machine (which never persists a default it already has) would delete it on
every round, and the two would ping-pong forever.

The embedding configuration this area also used to carry is gone: with no
vector index there is nothing it could configure (ADR knowledge-is-plain-files).
"""

from __future__ import annotations

import logging
from typing import Protocol

from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.domain.internal_engine_config import (
    AGGREGATE,
    ORGANISE,
    TIDY,
    GlobalInternalEngineConfig,
    UpkeepSetting,
)

logger = logging.getLogger(__name__)

AREA = "settings"

#: The one document this area holds (``state/settings/internal-engine.yaml``).
DOC = "internal-engine"


class _SingletonRow(Protocol):
    async def get(self) -> object | None: ...


#: The unattended passes, and the value each one has before anyone decides.
#: Listed rather than derived so "the defaults" is a fact this module states
#: once — it is what decides whether a machine publishes a document at all.
_PASSES = (AGGREGATE, ORGANISE, TIDY)
_PASS_DEFAULTS = {
    AGGREGATE: UpkeepSetting(enabled=True),
    ORGANISE: UpkeepSetting(enabled=True),
    TIDY: UpkeepSetting(enabled=False),
}


def _is_default(config: GlobalInternalEngineConfig) -> bool:
    """Whether the selection is what a machine has before anyone decides."""
    return (
        config.model is None
        and config.tidy_owner_machine_id is None
        and all(config.upkeep(name) == _PASS_DEFAULTS[name] for name in _PASSES)
    )


def _upkeep_from_doc(
    doc: dict[str, object], current: GlobalInternalEngineConfig
) -> dict[str, UpkeepSetting]:
    """The document's upkeep block, falling back to what this machine holds.

    A document written before upkeep travelled carries none of it, and must
    leave this machine's settings exactly as they are rather than resetting
    them to the defaults — an older machine in the fleet is not a decision.
    ``auto_tidy_enabled`` is still read from the top level for the same reason:
    that is where every document written so far put it.
    """
    raw = doc.get("upkeep")
    block = raw if isinstance(raw, dict) else {}
    out: dict[str, UpkeepSetting] = {}
    for name in _PASSES:
        held = current.upkeep(name)
        entry = block.get(name)
        if not isinstance(entry, dict):
            # The document says nothing about this pass. Tidy's switch still
            # has its old home at the top level, so a pre-upkeep document
            # carries that one; everything else stays as this machine has it.
            enabled = doc.get("auto_tidy_enabled") if name == TIDY else None
            out[name] = UpkeepSetting(
                enabled=held.enabled if enabled is None else bool(enabled),
                interval_s=held.interval_s,
            )
            continue
        # An entry that IS there is authoritative in both halves — including
        # ``interval_s: null``, which is a fleet-wide "back to the default"
        # and must clear an interval this machine chose.
        interval = entry.get("interval_s")
        out[name] = UpkeepSetting(
            enabled=bool(entry.get("enabled", held.enabled)),
            interval_s=int(interval) if isinstance(interval, int | float) else None,
        )
    return out


class EngineSettingsSyncState:
    """Implements ``application.sync.ports.SyncedStatePort`` structurally."""

    area = AREA

    def __init__(
        self,
        internal_engine: InternalEngineConfigService,
        *,
        internal_repo: _SingletonRow,
    ) -> None:
        self._internal = internal_engine
        self._internal_repo = internal_repo

    async def export_docs(self) -> tuple[list[tuple[str, dict[str, object]]], list[str]]:
        # Own (and publish) only a singleton this machine has actually
        # persisted: a fresh machine exporting a synthesized default would
        # same-path conflict with the fleet's value on its very first
        # unrelated-histories merge.
        if await self._internal_repo.get() is None:
            return [], []
        internal = await self._internal.get()
        # And only a non-default one: a persisted row holding the defaults is
        # the same decision as no row, and publishing it would be re-adding a
        # document every fresh machine deletes again (module docstring).
        if _is_default(internal):
            return [], []
        doc: dict[str, object] = {
            "model": internal.model,
            "auto_tidy_enabled": internal.auto_tidy_enabled,
            "tidy_owner_machine_id": internal.tidy_owner_machine_id,
            "upkeep": {
                name: {
                    "enabled": internal.upkeep(name).enabled,
                    "interval_s": internal.upkeep(name).interval_s,
                }
                for name in _PASSES
            },
        }
        return [(DOC, doc)], [DOC]

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[tuple[str, str]]:
        errors: list[tuple[str, str]] = []
        for path, doc in docs:
            if path != DOC:
                continue
            try:
                current = await self._internal.get()
                raw = doc.get("model")
                model = str(raw) if raw else None
                owner = doc.get("tidy_owner_machine_id", current.tidy_owner_machine_id)
                owner = str(owner) if isinstance(owner, str) and owner else None
                upkeep = _upkeep_from_doc(doc, current)
                if (
                    model == current.model
                    and owner == current.tidy_owner_machine_id
                    and all(upkeep[name] == current.upkeep(name) for name in _PASSES)
                ):
                    continue
                await self._internal.update(
                    model=model,
                    tidy_owner_machine_id=owner or "",
                    upkeep=upkeep,
                    actor="sync",
                )
            except Exception as e:
                errors.append((path, str(e)))
        return errors

    async def delete_docs(self, rels: list[str]) -> None:
        """Reset to the defaults: the fleet took its model choice back.

        The singleton has no "absent" state a row could express, so the reset
        is written through the service like any other change (audited as
        ``sync``). Nothing is written when the defaults already hold — the
        ordinary case, since a machine that holds them publishes no document
        and so never receives this deletion for a choice of its own.
        """
        if DOC not in rels:
            return
        if _is_default(await self._internal.get()):
            return
        logger.info("sync: internal-engine settings reset to defaults (deleted on another machine)")
        await self._internal.update(
            model=None,
            tidy_owner_machine_id="",
            upkeep=dict(_PASS_DEFAULTS),
            actor="sync",
        )

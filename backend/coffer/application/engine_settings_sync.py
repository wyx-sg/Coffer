"""Engine settings as a synced state area (spec vault-sync slice 7).

The internal-engine model choice is an installation-wide singleton that should
match across machines: Coffer's own passes behave the same everywhere only when
they run on the same model. Whether the tidy worker is armed travels with it,
since it is the same setting's other half.

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
from coffer.domain.internal_engine_config import GlobalInternalEngineConfig

logger = logging.getLogger(__name__)

AREA = "settings"

#: The one document this area holds (``state/settings/internal-engine.yaml``).
DOC = "internal-engine"


class _SingletonRow(Protocol):
    async def get(self) -> object | None: ...


def _is_default(config: GlobalInternalEngineConfig) -> bool:
    """Whether the selection is what a machine has before anyone decides."""
    return (
        config.model is None
        and not config.auto_tidy_enabled
        and config.tidy_owner_machine_id is None
    )


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
                auto_tidy = bool(doc.get("auto_tidy_enabled", current.auto_tidy_enabled))
                owner = doc.get("tidy_owner_machine_id", current.tidy_owner_machine_id)
                owner = str(owner) if isinstance(owner, str) and owner else None
                if (
                    model == current.model
                    and auto_tidy == current.auto_tidy_enabled
                    and owner == current.tidy_owner_machine_id
                ):
                    continue
                await self._internal.update(
                    model=model,
                    auto_tidy_enabled=auto_tidy,
                    tidy_owner_machine_id=owner or "",
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
            auto_tidy_enabled=False,
            tidy_owner_machine_id="",
            actor="sync",
        )

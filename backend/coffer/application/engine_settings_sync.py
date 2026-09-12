"""Engine settings as a synced state area (spec vault-export-import slice 7).

The internal-engine model choice is an installation-wide singleton that should
match across machines: Coffer's own passes behave the same everywhere only when
they run on the same model. Whether the tidy worker is armed travels with it,
since it is the same setting's other half.

The embedding configuration this area also used to carry is gone: with no
vector index there is nothing it could configure (ADR knowledge-is-plain-files).
"""

from __future__ import annotations

from typing import Protocol

from coffer.application.internal_engine_config_service import InternalEngineConfigService

AREA = "settings"


class _SingletonRow(Protocol):
    async def get(self) -> object | None: ...


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
        # unrelated-histories merge. Until the row exists locally, the doc is
        # preserved verbatim and applied at import like any foreign state.
        if await self._internal_repo.get() is None:
            return [], []
        internal = await self._internal.get()
        doc: dict[str, object] = {
            "model": internal.model,
            "auto_tidy_enabled": internal.auto_tidy_enabled,
        }
        return [("internal-engine", doc)], ["internal-engine"]

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[tuple[str, str]]:
        errors: list[tuple[str, str]] = []
        for path, doc in docs:
            if path != "internal-engine":
                continue
            try:
                current = await self._internal.get()
                raw = doc.get("model")
                model = str(raw) if raw else None
                auto_tidy = bool(doc.get("auto_tidy_enabled", current.auto_tidy_enabled))
                if model == current.model and auto_tidy == current.auto_tidy_enabled:
                    continue
                await self._internal.update(model=model, auto_tidy_enabled=auto_tidy, actor="sync")
            except Exception as e:
                errors.append((path, str(e)))
        return errors

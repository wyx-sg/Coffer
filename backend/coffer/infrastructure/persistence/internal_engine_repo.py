"""Coffer's own settings as a vault document (spec vault-storage).

What Coffer may run unattended and how often, and the speech-to-text model:
every field is a decision the person made for the whole fleet, so the
settings are one vault document,
``state/settings/internal-engine.json``::

    {"format_version": 1, "transcribe_model": null,
     "upkeep": {"memory_sync": {"enabled": true, "interval_s": null}}}

A document written by an older version may carry ``model``,
``curate_owner_machine_id``, ``model_timeout_s``, ``upkeep.curate`` or
``upkeep.distil``. They are ignored on read, and the next write rebuilds the
document from the fields above, which drops them (spec internal-engine "Ignore
retired keys in the settings document"). ``upkeep.aggregate`` is the one that
carries over: with no ``upkeep.memory_sync`` beside it, its switch and
interval are read as the memory sync's (the memory sync replaced it).

A vault that never chose anything has no document, and reads as the defaults
(``get`` answers ``None``); a change back to every default removes the
document, so "the defaults" is always the absence of one. ``updated_at`` is
not in the document — two machines stamping it would conflict on every edit — so it is local, in
``local/engine.json``: when *this* machine last changed the settings.

Each setter writes only its own fields: read-modify-write against ``HEAD``, so
a change restating fields the caller never looked at cannot undo another
machine's edit that arrived meanwhile.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coffer.domain.internal_engine_config import (
    MEMORY_SYNC,
    RETIRED_AGGREGATE,
    GlobalInternalEngineConfig,
    UpkeepSetting,
)
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.json_store import JsonStore
from coffer.infrastructure.vault.state_documents import StateDocument

AREA = "settings"
DOC = "internal-engine"
_PASSES = (MEMORY_SYNC,)
#: Top-level keys an older build wrote. A write names each as ``None``, which
#: the document encoder reads as "remove it from the file".
_RETIRED_KEYS = ("model", "curate_owner_machine_id", "model_timeout_s")


def engine_local_path() -> Path:
    return local_root() / "engine.json"


def _int(raw: Any) -> int | None:
    return int(raw) if isinstance(raw, int | float) and not isinstance(raw, bool) else None


def _str(raw: Any) -> str | None:
    return raw if isinstance(raw, str) and raw else None


def _upkeep(doc: Mapping[str, Any], name: str) -> UpkeepSetting:
    block = doc.get("upkeep")
    entry = block.get(name) if isinstance(block, dict) else None
    if not isinstance(entry, dict) and name == MEMORY_SYNC and isinstance(block, dict):
        entry = block.get(RETIRED_AGGREGATE)
    if not isinstance(entry, dict):
        return UpkeepSetting(enabled=True)
    return UpkeepSetting(
        enabled=entry.get("enabled", True) is not False, interval_s=_int(entry.get("interval_s"))
    )


def _to_domain(doc: Mapping[str, Any], updated_at: datetime) -> GlobalInternalEngineConfig:
    memory_sync = _upkeep(doc, MEMORY_SYNC)
    return GlobalInternalEngineConfig(
        updated_at=updated_at,
        memory_sync_enabled=memory_sync.enabled,
        memory_sync_interval_s=memory_sync.interval_s,
        transcribe_model=_str(doc.get("transcribe_model")),
    )


def _to_doc(config: GlobalInternalEngineConfig) -> dict[str, Any]:
    return {
        "transcribe_model": config.transcribe_model,
        "upkeep": {
            name: {
                "enabled": config.upkeep(name).enabled,
                "interval_s": config.upkeep(name).interval_s,
            }
            for name in _PASSES
        },
    }


#: What a vault that never chose anything holds, as a document.
_DEFAULT_DOC = _to_doc(_to_domain({}, datetime.fromtimestamp(0, tz=UTC)))


class VaultInternalEngineConfigRepo:
    """``InternalEngineConfigRepo`` over ``state/settings/internal-engine.json``."""

    def __init__(
        self,
        *,
        home: Path | None = None,
        local_path: Path | Callable[[], Path] = engine_local_path,
    ) -> None:
        self.document = StateDocument(AREA, DOC, home=home)
        self._local = JsonStore(local_path)

    def _updated_at(self) -> datetime:
        raw = self._local.read().get("updated_at")
        if isinstance(raw, str):
            try:
                value = datetime.fromisoformat(raw)
                return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
            except ValueError:
                pass
        return datetime.now(tz=UTC)

    async def get(self) -> GlobalInternalEngineConfig | None:
        doc = self.document.get()
        return _to_domain(doc, self._updated_at()) if doc is not None else None

    def _change(
        self, summary: str, change: Callable[[GlobalInternalEngineConfig], dict[str, Any]]
    ) -> GlobalInternalEngineConfig:
        now = datetime.now(tz=UTC)
        current = _to_domain(self.document.get() or {}, now)
        doc = {**_to_doc(current), **change(current)}
        if doc == _DEFAULT_DOC:
            # Back to the defaults is the same decision as never choosing:
            # no document, so a fresh machine and this one agree.
            self.document.remove(summary=summary)
        else:
            self.document.put({**doc, **dict.fromkeys(_RETIRED_KEYS)}, summary=summary)
        self._local.write({"updated_at": now.isoformat()})
        return _to_domain(self.document.get() or doc, now)

    async def set(
        self, *, upkeep: Mapping[str, UpkeepSetting] | None = None
    ) -> GlobalInternalEngineConfig:
        def change(current: GlobalInternalEngineConfig) -> dict[str, Any]:
            out: dict[str, Any] = {}
            if upkeep:
                block = _to_doc(current)["upkeep"]
                for name, setting in upkeep.items():
                    block[name] = {"enabled": setting.enabled, "interval_s": setting.interval_s}
                out["upkeep"] = block
            return out

        return self._change("Changed the internal engine's settings", change)

    async def set_transcribe_model(self, model: str | None) -> GlobalInternalEngineConfig:
        """Write only the transcription model. ``None`` stops transcription."""
        return self._change(
            "Changed the transcription model", lambda _c: {"transcribe_model": model}
        )


__all__ = ["VaultInternalEngineConfigRepo", "engine_local_path"]

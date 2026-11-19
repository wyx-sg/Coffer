"""Coffer's own settings as a vault document (spec vault-storage).

The speech-to-text model is a decision the person made for the whole fleet,
so the settings are one vault document, ``state/settings/internal-engine.json``::

    {"format_version": 1, "transcribe_model": null}

A document written by an older version may carry ``model``,
``curate_owner_machine_id``, ``model_timeout_s`` or ``upkeep`` (the switch and
timer of a retired memory pass). They are ignored on read, and the next write
rebuilds the document from the field above, which drops them (spec
internal-engine "Ignore retired keys in the settings document").

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

from coffer.domain.internal_engine_config import GlobalInternalEngineConfig
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.json_store import JsonStore
from coffer.infrastructure.vault.state_documents import StateDocument

AREA = "settings"
DOC = "internal-engine"
#: Top-level keys an older build wrote. A write names each as ``None``, which
#: the document encoder reads as "remove it from the file".
_RETIRED_KEYS = ("model", "curate_owner_machine_id", "model_timeout_s", "upkeep")


def engine_local_path() -> Path:
    return local_root() / "engine.json"


def _str(raw: Any) -> str | None:
    return raw if isinstance(raw, str) and raw else None


def _to_domain(doc: Mapping[str, Any], updated_at: datetime) -> GlobalInternalEngineConfig:
    return GlobalInternalEngineConfig(
        updated_at=updated_at,
        transcribe_model=_str(doc.get("transcribe_model")),
    )


def _to_doc(config: GlobalInternalEngineConfig) -> dict[str, Any]:
    return {"transcribe_model": config.transcribe_model}


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

    async def set_transcribe_model(self, model: str | None) -> GlobalInternalEngineConfig:
        """Write only the transcription model. ``None`` stops transcription."""
        return self._change(
            "Changed the transcription model", lambda _c: {"transcribe_model": model}
        )


__all__ = ["VaultInternalEngineConfigRepo", "engine_local_path"]

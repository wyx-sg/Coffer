from __future__ import annotations

import contextlib
import os
from typing import Any

from coffer.application.memory.auto_organize import MemoryAutoOrganizer

AUTO_ORGANIZE_ENV = "COFFER_MEMORY_AUTO_ORGANIZE"
_FALSY = {"0", "false", "no", "off"}


def auto_organize_enabled() -> bool:
    """Default-ON (FR-035): enabled unless ``COFFER_MEMORY_AUTO_ORGANIZE`` is
    explicitly falsy. The write→organize→固化 pipeline runs automatically (the
    no-manual principle); the env var is only an off-switch."""
    return os.environ.get(AUTO_ORGANIZE_ENV, "").strip().lower() not in _FALSY


def start_auto_organize(app: Any, memory_service: Any, organizer: Any) -> None:
    """Default-ON. Unless disabled via the env off-switch, install the debounced
    auto-organizer on the memory write-notify hook and stash it on app.state for
    teardown."""
    if not auto_organize_enabled():
        return
    auto = MemoryAutoOrganizer(organize=organizer)
    memory_service.set_on_change(auto.on_change)
    app.state.auto_organizer = auto


async def stop_auto_organize(app: Any) -> None:
    """Best-effort: cancel any pending debounce timer (never fires organize at
    shutdown; never blocks teardown)."""
    auto = getattr(app.state, "auto_organizer", None)
    if auto is None:
        return
    with contextlib.suppress(Exception):
        await auto.shutdown()

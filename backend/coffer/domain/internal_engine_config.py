"""Coffer's own operating settings: the work it does unattended and which model
transcribes speech (spec
internal-engine "Carry a switch and interval for each unattended pass")."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: The pass Coffer runs on its own behalf: the memory sync (spec memory "Sync
#: on an interval and on demand"). Named here rather than in the worker so a
#: surface can offer it without importing an application module.
MEMORY_SYNC = "memory_sync"
#: The retired layer's aggregation pass. A settings document an older build
#: wrote may still carry it; its switch and interval become the memory sync's.
RETIRED_AGGREGATE = "aggregate"


@dataclass(frozen=True)
class UpkeepSetting:
    """One unattended pass's switch and timer.

    ``interval_s`` is ``None`` until the operator chooses one, and ``None``
    means "whatever the pass's own default is". The default therefore stays in
    one place — the worker that owns the pass — and raising it later raises it
    for every vault that never chose, rather than for none of them.
    """

    enabled: bool
    interval_s: int | None = None


@dataclass
class GlobalInternalEngineConfig:
    """The one global set of Coffer's own settings: what it may run
    unattended and the speech-to-text model."""

    updated_at: datetime
    #: The memory sync. On by default: the first sync on a machine, and any
    #: large one, waits for the person to confirm a preview before it writes
    #: into an agent (spec memory "Preview a first or large sync").
    memory_sync_enabled: bool = True
    memory_sync_interval_s: int | None = None
    #: The speech-to-text model, on the connection marked ``transcribe_default``
    #: (spec internal-engine "Transcribe speech on its own connection and
    #: model"). ``None`` until the operator picks one,
    #: and while it is ``None`` Coffer transcribes nothing.
    transcribe_model: str | None = None

    def upkeep(self, pass_name: str) -> UpkeepSetting:
        """One pass's switch and timer, by the names above.

        A surface asks for a pass by name rather than reaching for its
        fields, so adding a pass adds one entry here instead of a branch in
        every reader.
        """
        if pass_name == MEMORY_SYNC:
            return UpkeepSetting(self.memory_sync_enabled, self.memory_sync_interval_s)
        raise ValueError(f"unknown upkeep pass: {pass_name}")

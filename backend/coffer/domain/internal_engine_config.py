"""Coffer's own operating settings: the work it does unattended and which model
transcribes speech (spec
internal-engine "Carry a switch and interval for each of the two unattended passes")."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: The passes Coffer runs on its own behalf, and where each one's built-in
#: interval lives. Named here rather than in the workers so a surface can offer
#: exactly these two without importing two application modules.
AGGREGATE = "aggregate"
DISTIL = "distil"


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
    #: Aggregation (spec memory "Aggregate on an interval and on demand"): reads
    #: the agents' own memory files and
    #: writes only the derived tree, so it defaults ON — there is no unattended
    #: REWRITE here for an operator to consent to.
    auto_aggregate_enabled: bool = True
    aggregate_interval_s: int | None = None
    #: The distil pass (spec memory "Distil each raw entry into a note mechanically"): it
    #: rewrites the derived digest, which "Keep the memory tree derived
    #: and local" makes reproducible by deleting and re-running, so
    #: this defaults ON for the same reason.
    auto_distil_enabled: bool = True
    distil_interval_s: int | None = None
    #: The speech-to-text model, on the connection marked ``transcribe_default``
    #: (spec internal-engine "Transcribe speech on its own connection and
    #: model"). ``None`` until the operator picks one,
    #: and while it is ``None`` Coffer transcribes nothing.
    transcribe_model: str | None = None

    def upkeep(self, pass_name: str) -> UpkeepSetting:
        """One pass's switch and timer, by the names above.

        A surface asks for a pass by name rather than reaching for one of four
        fields, so adding a pass adds one entry here instead of a branch in
        every reader.
        """
        if pass_name == AGGREGATE:
            return UpkeepSetting(self.auto_aggregate_enabled, self.aggregate_interval_s)
        if pass_name == DISTIL:
            return UpkeepSetting(self.auto_distil_enabled, self.distil_interval_s)
        raise ValueError(f"unknown upkeep pass: {pass_name}")

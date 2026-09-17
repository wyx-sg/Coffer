"""Coffer's own operating settings: the engine it thinks with, and the work it
does unattended (spec provider-switching amendment 2026-06-22b).

Coffer's own internal LLM engine — the knowledge curation pass, and whatever
else Coffer runs on its own behalf — uses the connection flagged
``internal_default`` for its endpoint + key + wire, but the MODEL it uses is
chosen separately here; the connection carries no model of its own to fall back
on. ``model`` is ``None`` until the operator picks one, and while it is ``None``
the engine has nothing to run on and every pass it drives is a no-op."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: The fixed primary key of the singleton ``internal_engine_config`` row.
SINGLETON_ID = 1


#: The passes Coffer runs on its own behalf, and where each one's built-in
#: interval lives. Named here rather than in the workers so a surface can offer
#: exactly these three without importing three application modules.
AGGREGATE = "aggregate"
DISTIL = "distil"
CURATE = "curate"


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
    """The one global internal-engine model selection, and what it may run
    unattended.

    ``auto_curate_enabled`` lives here rather than on a collection because it
    governs the engine, not a directory: it decides whether Coffer's own model
    may read a collection's ``sources/`` and derive its ``topics/`` on a timer
    with no review step (spec knowledge FR-021).

    It ships **on**, which inverts what the pass it replaces did. Tidy rewrote
    the user's own knowledge files, so an operator had to switch it on
    deliberately. Curation may not touch a source at all — it reads
    ``sources/`` and writes only ``topics/``, a lane that is rebuilt from
    scratch by deleting it and running again — and it is the ONLY path from a
    source to something an agent can read. Shipping it off would leave every
    new vault with a readable lane that is empty forever.

    ``curate_owner_machine_id`` names the single machine allowed to run that
    pass once a vault spans several (spec vault-sync ``## Unattended
    rewriters``). Without it, two machines fold the same pair of sources into
    two *different* topic documents; git merges that cleanly — the two topics
    are additions at different paths — and the vault silently ends up holding
    the same knowledge twice. That is a duplicate no conflict can catch, so the
    fix has to be that only one machine ever writes.

    ``None`` means "wherever this setting is read", which is the right answer
    for a single-machine vault and the reason curation running by default does
    not force a choice before there is anything to choose between.
    """

    model: str | None
    updated_at: datetime
    auto_curate_enabled: bool = True
    curate_owner_machine_id: str | None = None
    #: Aggregation (spec memory FR-007): reads the agents' own memory files and
    #: writes only the derived tree, so it defaults ON — there is no unattended
    #: REWRITE here for an operator to consent to.
    auto_aggregate_enabled: bool = True
    aggregate_interval_s: int | None = None
    #: The distil pass (spec memory FR-030): the model rewrites the derived
    #: digest, which FR-023 makes reproducible by deleting and re-running, so
    #: this defaults ON for the same reason.
    auto_distil_enabled: bool = True
    distil_interval_s: int | None = None
    #: Curation's own timer. Its SWITCH is ``auto_curate_enabled`` above.
    curate_interval_s: int | None = None
    #: How long one call to Coffer's own model may take before the caller gives
    #: up, or ``None`` for the built-in default (spec internal-engine FR-022).
    #: ``None`` means the same thing it means for an interval — the default
    #: lives in one place and raising it later reaches every vault that never
    #: chose — and for the same reason: the right number is a property of the
    #: operator's endpoint, not of Coffer, and a gateway twice as slow as the
    #: one this was written against turns a bounded pass into a useless one.
    model_timeout_s: int | None = None
    #: The speech-to-text model, on the connection marked ``transcribe_default``
    #: (spec internal-engine FR-025). ``None`` until the operator picks one,
    #: and while it is ``None`` Coffer transcribes nothing — the same "both
    #: halves or neither" rule the engine model follows.
    transcribe_model: str | None = None

    def upkeep(self, pass_name: str) -> UpkeepSetting:
        """One pass's switch and timer, by the names above.

        A surface asks for a pass by name rather than reaching for one of six
        fields, so adding a pass adds one entry here instead of a branch in
        every reader.
        """
        if pass_name == AGGREGATE:
            return UpkeepSetting(self.auto_aggregate_enabled, self.aggregate_interval_s)
        if pass_name == DISTIL:
            return UpkeepSetting(self.auto_distil_enabled, self.distil_interval_s)
        if pass_name == CURATE:
            return UpkeepSetting(self.auto_curate_enabled, self.curate_interval_s)
        raise ValueError(f"unknown upkeep pass: {pass_name}")

    def curate_runs_on(self, machine_id: str | None) -> bool:
        """Whether the timer may run a curation pass on this machine.

        An owner that names a machine this vault has never heard of stops
        curation everywhere, which is the safe direction: no curation costs a
        stale ``topics/`` lane, curation on every machine costs duplicated
        knowledge no merge can see.
        """
        if not self.auto_curate_enabled:
            return False
        if self.curate_owner_machine_id is None:
            return True
        return self.curate_owner_machine_id == machine_id

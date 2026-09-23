"""Coffer's own operating settings: the engine it thinks with, and the work it
does unattended (spec internal-engine "Resolve the engine's connection and
model together").

Coffer's own internal LLM engine — the knowledge curation pass, and whatever
else Coffer runs on its own behalf — uses the connection flagged
``internal_default`` for its endpoint + key + wire, but the MODEL it uses is
chosen separately here; the connection carries no model of its own to fall back
on. ``model`` is ``None`` until the operator picks one, and while it is ``None``
the engine has nothing to run on and every pass it drives is a no-op."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

#: The fixed primary key of the singleton ``internal_engine_config`` row.
SINGLETON_ID = 1


class CurationOwner(StrEnum):
    """What ``curate_owner_machine_id`` IS, from this machine's point of view.

    The same four **states** a channel's machine binding has (frontend
    ``lib/machineBinding.ts``, spec channels "Bind each channel to the one machine that
    runs it"), because the two facts have the same shape — one machine named in a
    document every machine holds — and must not grow two ways of resolving it.

    The state NAMES are not shared, and that is deliberate rather than drift.
    A channel with no machine named is ``unbound``; a pass with none is
    ``UNOWNED``, because what is missing is an owner and not a binding. Both
    words reach a user — this one through ``coffer engine curate-owner show
    --json`` — so neither may be "corrected" into the other. What must stay
    identical is the rule that picks between them, not the spelling.

    ``UNKNOWN`` is the only one that is a **fault**. The owner names a machine
    no registry entry claims, so no timer anywhere will run the pass and
    nothing else in the product will say why. It is reported rather than
    quietly folded into ``OTHER``, which is exactly the difference between "it
    is running somewhere else" and "it is running nowhere".

    One state differs from the channel's in what it *does*, and the difference
    is deliberate. An unbound channel runs **nowhere**, because answering a
    platform twice cannot be walked back. An unowned curation pass runs
    **here**, because a vault that has never named an owner is a vault with one
    machine, and the cost of being wrong is a duplicated document rather
    than a bot answering itself.
    """

    UNOWNED = "unowned"
    SELF = "self"
    OTHER = "other"
    UNKNOWN = "unknown"


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
    may merge new material into a collection's documents, and carry a
    person's edit through the rest of them, on a timer with no review step
    (spec knowledge "Curate through a fenced four-tool pass").

    It ships **on**: curation is what turns the material an upload or an
    agent's ``coffer__write`` leaves in a collection's inbox into documents an
    agent reads. Shipping it off would leave every new vault's material
    waiting unread. (With no internal model configured, material becomes a
    document as it stands, so nothing depends on this switch for that.)

    ``curate_owner_machine_id`` names the single machine allowed to run that
    pass once a vault spans several (spec vault-sync
    "Run an unattended rewriter on one owner machine"). Without it, two
    machines fold the same material into two *different* documents; git
    merges that cleanly — the two documents are additions at different
    paths — and the vault silently ends up holding the same knowledge twice. That is a
    duplicate no conflict can catch, so the fix has to be that only one machine ever
    writes.

    ``None`` means "wherever this setting is read", which is the right answer
    for a single-machine vault and the reason curation running by default does
    not force a choice before there is anything to choose between.
    """

    model: str | None
    updated_at: datetime
    auto_curate_enabled: bool = True
    curate_owner_machine_id: str | None = None
    #: Aggregation (spec memory "Aggregate on an interval and on demand"): reads
    #: the agents' own memory files and
    #: writes only the derived tree, so it defaults ON — there is no unattended
    #: REWRITE here for an operator to consent to.
    auto_aggregate_enabled: bool = True
    aggregate_interval_s: int | None = None
    #: The distil pass (spec memory "Distil incrementally in two stages"): the
    #: model rewrites the derived digest, which "Keep the memory tree derived
    #: and local" makes reproducible by deleting and re-running, so
    #: this defaults ON for the same reason.
    auto_distil_enabled: bool = True
    distil_interval_s: int | None = None
    #: Curation's own timer. Its SWITCH is ``auto_curate_enabled`` above.
    curate_interval_s: int | None = None
    #: How long one call to Coffer's own model may take before the caller gives
    #: up, or ``None`` for the built-in default (spec internal-engine "Carry the
    #: bound on one model call").
    #: ``None`` means the same thing it means for an interval — the default
    #: lives in one place and raising it later reaches every vault that never
    #: chose — and for the same reason: the right number is a property of the
    #: operator's endpoint, not of Coffer, and a gateway twice as slow as the
    #: one this was written against turns a bounded pass into a useless one.
    model_timeout_s: int | None = None
    #: The speech-to-text model, on the connection marked ``transcribe_default``
    #: (spec internal-engine "Transcribe speech on its own connection and
    #: model"). ``None`` until the operator picks one,
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
        curation everywhere, which is the safe direction: no curation costs
        material waiting in the inbox, curation on every machine costs
        duplicated knowledge no merge can see.
        """
        if not self.auto_curate_enabled:
            return False
        if self.curate_owner_machine_id is None:
            return True
        return self.curate_owner_machine_id == machine_id

    def curation_owner(self, machine_id: str | None, known: Collection[str] = ()) -> CurationOwner:
        """Which of the four states the owner is in, for a surface to report.

        Deliberately separate from :meth:`curate_runs_on`, which answers the
        timer and may only ever say yes or no. This answers the **user**, and
        the two questions it can tell apart that a boolean cannot are the whole
        reason it exists: "another machine is doing it" and "nobody is doing
        it, because the machine named no longer exists" both read as "not here"
        to the timer, and only one of them is something to fix.

        ``known`` is every machine id the registry holds, and this is
        deliberately the **same rule, statement for statement**, as the
        frontend's ``bindingState`` in ``lib/machineBinding.ts``. Two facts of
        one shape resolving by two rules is worse than either rule: a reader
        would have to learn which surface to believe.

        An **empty** registry can never yield ``UNKNOWN``, and the reason is
        what ``UNKNOWN`` claims. A non-empty registry that does not hold the
        owner has **shown** that no machine claims that id. An empty one has
        shown nothing — there is no registry when no remote is configured, and
        none for a moment after the working tree is rebuilt. Reporting "no
        machine claims this" from "we cannot say" is overclaiming, and it is
        overclaiming the one state that is a fault.

        ``auto_curate_enabled`` is not consulted. Whether the pass is switched
        on and where it would run are two facts, and a surface that hid the
        owner while the switch was off would hide it precisely when someone is
        about to turn it on.
        """
        owner = self.curate_owner_machine_id
        if owner is None:
            return CurationOwner.UNOWNED
        if owner == machine_id:
            return CurationOwner.SELF
        if not known or owner in known:
            return CurationOwner.OTHER
        return CurationOwner.UNKNOWN

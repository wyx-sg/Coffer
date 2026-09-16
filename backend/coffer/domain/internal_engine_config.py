"""Coffer's own operating settings: the engine it thinks with, and the work it
does unattended (spec provider-switching amendment 2026-06-22b).

Coffer's own internal LLM engine — the notes tidy pass, and whatever else
Coffer runs on its own behalf — uses the connection flagged ``internal_default``
for its endpoint + key + wire, but the MODEL it uses is chosen separately here;
the connection carries no model of its own to fall back to. ``model`` is
``None`` until the operator picks one, and while it is ``None`` the engine has
nothing to run on and every pass it drives is a no-op."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: The fixed primary key of the singleton ``internal_engine_config`` row.
SINGLETON_ID = 1


#: The passes Coffer runs on its own behalf, and where each one's built-in
#: interval lives. Named here rather than in the workers so a surface can offer
#: exactly these three without importing three application modules.
AGGREGATE = "aggregate"
ORGANISE = "organise"
TIDY = "tidy"


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

    ``auto_tidy_enabled`` lives here rather than on a collection because it
    governs the engine, not a directory: it decides whether Coffer's own model
    may rewrite the user's knowledge files on a timer with no review step
    (spec knowledge FR-031). It ships **off**, so an unattended rewriter is
    something the operator switches on rather than something they discover
    running.

    ``tidy_owner_machine_id`` names the single machine allowed to run that
    rewriter once a vault spans several (spec vault-sync ``## Unattended
    rewriters``). Without it, two machines merge the same pair of notes into two
    *different* topic documents; git merges that cleanly — both agree the
    sources are deleted, and the two topics are additions at different paths —
    and the vault silently ends up holding the same knowledge twice. That is a
    duplicate no conflict can catch, so the fix has to be that only one machine
    ever writes.

    ``None`` means "wherever this setting is read", which is the right answer
    for a single-machine vault and the reason enabling tidy does not force a
    choice before there is anything to choose between.
    """

    model: str | None
    updated_at: datetime
    auto_tidy_enabled: bool = False
    tidy_owner_machine_id: str | None = None
    #: Aggregation (spec memory FR-007): reads the agents' own memory files and
    #: writes only the derived tree, so it defaults ON — there is no unattended
    #: REWRITE here for an operator to consent to.
    auto_aggregate_enabled: bool = True
    aggregate_interval_s: int | None = None
    #: The organise pass (spec memory FR-017): the model rewrites the derived
    #: digest, which spec memory FR-016 makes reproducible by deleting and
    #: re-running, so this defaults ON for the same reason.
    auto_organise_enabled: bool = True
    organise_interval_s: int | None = None
    #: Tidy's own timer. Its SWITCH is ``auto_tidy_enabled`` above and ships
    #: off, because tidy rewrites the user's own knowledge files.
    tidy_interval_s: int | None = None

    def upkeep(self, pass_name: str) -> UpkeepSetting:
        """One pass's switch and timer, by the names above.

        A surface asks for a pass by name rather than reaching for one of six
        fields, so adding a pass adds one entry here instead of a branch in
        every reader.
        """
        if pass_name == AGGREGATE:
            return UpkeepSetting(self.auto_aggregate_enabled, self.aggregate_interval_s)
        if pass_name == ORGANISE:
            return UpkeepSetting(self.auto_organise_enabled, self.organise_interval_s)
        if pass_name == TIDY:
            return UpkeepSetting(self.auto_tidy_enabled, self.tidy_interval_s)
        raise ValueError(f"unknown upkeep pass: {pass_name}")

    def tidy_runs_on(self, machine_id: str | None) -> bool:
        """Whether the timer may run a pass on this machine.

        An owner that names a machine this vault has never heard of stops tidy
        everywhere, which is the safe direction: no tidy costs a little
        housekeeping, tidy on every machine costs duplicated knowledge.
        """
        if not self.auto_tidy_enabled:
            return False
        if self.tidy_owner_machine_id is None:
            return True
        return self.tidy_owner_machine_id == machine_id

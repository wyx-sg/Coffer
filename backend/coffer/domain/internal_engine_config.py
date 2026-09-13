"""The single, global internal-engine model selection (spec provider-switching amendment
2026-06-22b).

Coffer's own internal LLM engine — the notes tidy pass, and whatever else
Coffer runs on its own behalf — uses the connection flagged ``internal_default``
for its
endpoint + key + wire, but the MODEL it uses is chosen separately here — the
connection no longer carries a model. ``model`` is ``None`` until the operator
picks one, in which case the engine falls back to the connection's model during
rollout (removed once the connection's model field is dropped)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: The fixed primary key of the singleton ``internal_engine_config`` row.
SINGLETON_ID = 1


@dataclass
class GlobalInternalEngineConfig:
    """The one global internal-engine model selection, and what it may run
    unattended.

    ``auto_tidy_enabled`` lives here rather than on a collection because it
    governs the engine, not a directory: it decides whether Coffer's own model
    may rewrite the user's knowledge files on a timer with no review step
    (spec knowledge FR-051). It ships **off**, so an unattended rewriter is
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

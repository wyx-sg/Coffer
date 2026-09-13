"""This machine's answer to ``coffer.domain.scope`` (spec vault-sync "Scope").

``domain.scope`` decides activation from two facts: the session's agent, and
the machine the daemon is running on. The first varies per call; the second is
one fixed fact for the life of the process. Threading it through every call
site would be the same argument written nine times with nine chances to forget
it — and a forgotten machine id reads as "no machine", which silently makes
machine-scoped resources dormant.

So the machine id is bound once, here, into an object the composition root
builds (``machine_id.resolve``) and hands to the few services that ask the
question. It holds no other state and mutates nothing, so a test builds one
with any id — including one that matches nothing — and gets a deterministic
answer without touching the host.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.domain.scope import ExclusionAxis, Scope, excluded_by, is_active


@dataclass(frozen=True)
class ScopeEvaluator:
    """``domain.scope``'s two predicates, with this machine already bound."""

    #: The derived id of the machine this daemon runs on. ``None`` only where
    #: a caller genuinely has no machine identity (a test, a CLI probe); such
    #: a caller matches only an unrestricted machine axis, i.e. sees strictly
    #: less, never more.
    machine_id: str | None

    def is_active(self, scope: Scope | None, agent: str | None) -> bool:
        """Whether a resource carrying ``scope`` activates for ``agent`` here."""
        return is_active(scope, agent=agent, machine=self.machine_id)

    def excluded_by(self, scope: Scope | None, agent: str | None) -> ExclusionAxis | None:
        """Which axis kept the resource dormant here, or None when it is active."""
        return excluded_by(scope, agent=agent, machine=self.machine_id)

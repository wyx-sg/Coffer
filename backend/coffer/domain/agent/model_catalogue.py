"""``AgentModel`` — one selectable model for a managed agent.

Deliberately *only* the shape. Coffer carries no model table of its own: every
id, label and description is read back from the agent that will run it (its
compiled-in catalog, its own ``model/list`` RPC, or its config file). A list
written down here went stale the day a CLI shipped a new tier, and it could not
tell two releases of the same tier apart either — which is the one thing a
picker has to show. See ``infrastructure/agent/`` for the discovery adapters and
``application/agent/model_catalogue`` for how they are composed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentModel:
    """One selectable model for a managed agent.

    Every entry is something the agent itself reported and will accept as
    ``--model``. An ``id`` is therefore whatever that agent calls the choice:
    Claude Code offers its tier ALIASES (``opus``, ``sonnet``, …) because those
    are what its own picker offers and what it resolves against the account at
    turn time, so the ``label`` is what the alias means today ("Opus 5"); Codex
    reports versioned ids and labels them itself. Coffer neither translates nor
    validates either — a model name typed anywhere is passed to the CLI
    verbatim, and the CLI owns that namespace.
    """

    id: str
    label: str = ""
    description: str = ""
    #: The reasoning-effort levels this model can be run at, in the order the
    #: agent reported them, or empty when it takes no such setting. An effort is
    #: not part of the model NAME — Codex's app-server carries it as its own
    #: field on a turn — so it travels beside the id all the way down.
    efforts: tuple[str, ...] = ()
    #: The level the agent itself would use when none is chosen; ``None`` when
    #: it named none (or when there are no efforts at all).
    default_effort: str | None = None


__all__ = ["AgentModel"]

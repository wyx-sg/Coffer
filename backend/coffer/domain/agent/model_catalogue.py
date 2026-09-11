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

    Every entry is a concrete model the agent itself reported. The CLIs' tier
    ALIASES (``sonnet``, ``opus``, ``best``, ``sonnet[1m]``, …) are deliberately
    not entries: each resolves to a model already listed, so carrying them made
    the picker a list of duplicates. They stay typeable — the CLI validates
    whatever ``--model`` is given — they are just not offered.
    """

    id: str
    label: str = ""
    description: str = ""


__all__ = ["AgentModel"]

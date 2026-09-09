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

    ``source`` says what kind of entry this is, and matches the wire contract's
    enum: ``"alias"`` for a moving pointer the CLI accepts (it resolves to the
    newest model in a tier, so it never names a version), ``"discovered"`` for a
    concrete, version-bearing model the agent told us about.
    """

    id: str
    label: str = ""
    description: str = ""
    source: str = "alias"


__all__ = ["AgentModel"]

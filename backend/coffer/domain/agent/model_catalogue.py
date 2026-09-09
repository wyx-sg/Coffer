"""Curated model catalogue per managed agent type — the half Coffer knows a
priori, before it looks at anything on disk.

Coffer used to carry a hardcoded model list in two unrelated places (the channel
``/model`` card and the web picker), which went stale the moment a CLI shipped a
new tier. This module is the single curated source; the discovered half (what
the agent's own config file advertises) is merged on top in
``application/agent/model_catalogue``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentModel:
    """One selectable model for a managed agent.

    ``source`` says where the entry came from: ``"alias"`` for a curated entry
    below, ``"discovered"`` for one read out of the agent's own config.
    """

    id: str
    label: str = ""
    description: str = ""
    source: str = "alias"


CURATED_MODELS: dict[str, tuple[AgentModel, ...]] = {
    # These are exactly the aliases `claude --model` documents and accepts — not
    # pinned model ids. An alias always resolves to the NEWEST model in its tier,
    # which is why this curated list does not go stale the way a list of pinned
    # ids does: a new Opus release changes what `opus` points at, not this table.
    # Anything version-specific the local CLI knows about arrives through
    # discovery instead.
    "claude_code": (
        AgentModel("fable", "Fable", "Most capable — hardest, longest-running tasks"),
        AgentModel("opus", "Opus", "Top-tier reasoning for complex work"),
        AgentModel("opusplan", "Opus Plan", "Opus while planning, Sonnet to execute"),
        AgentModel("sonnet", "Sonnet", "Balanced default for everyday coding"),
        AgentModel("haiku", "Haiku", "Fastest and cheapest for simple tasks"),
    ),
    # Codex names concrete models rather than tier aliases and exposes no
    # published alias set, so this stays the list Coffer has always offered.
    "codex": (
        AgentModel("gpt-5-codex", "GPT-5 Codex", "Codex-tuned model for coding work"),
        AgentModel("gpt-5", "GPT-5", "General-purpose flagship model"),
        AgentModel("o3", "o3", "Reasoning model for harder problems"),
    ),
}


def curated_for(agent_key: str) -> tuple[AgentModel, ...]:
    """The curated models for ``agent_key``; empty for an agent Coffer has no
    curated list for (the catalogue is then whatever discovery finds)."""
    return CURATED_MODELS.get(agent_key, ())


__all__ = ["CURATED_MODELS", "AgentModel", "curated_for"]

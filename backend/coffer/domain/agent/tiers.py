"""Claude Code's model tiers, and the model Coffer suggests for each.

Claude Code asks for models by TIER — ``opus``, ``sonnet``, ``haiku`` (which
also runs its background tasks: titles, summaries, classifiers) and ``fable`` —
and each tier resolves through ``ANTHROPIC_DEFAULT_<TIER>_MODEL``. On an
endpoint that serves no Claude ids, a tier left unpinned sends a Claude id and
fails, and behind a custom base URL the background model is the MAIN model
unless Haiku is pinned — a silent cost multiplier. So while an agent is on a
connection rather than its built-in login, every tier gets a model (spec
provider-switching "Suggest a model for each Claude Code tier").

Part of the agent vocabulary because the tiers are Claude Code's; the
suggestion reads only model ids, so it needs nothing from the provider kind.
"""

from __future__ import annotations

from collections.abc import Sequence

#: The tier names, in the order the Model tab shows them.
CLAUDE_TIERS: tuple[str, ...] = ("opus", "sonnet", "haiku", "fable")


def tier_env_key(tier: str) -> str:
    """The Claude Code environment variable that pins ``tier``."""
    return f"ANTHROPIC_DEFAULT_{tier.upper()}_MODEL"


def is_claude_model_id(model: str) -> bool:
    """Whether ``model`` looks like a Claude id (or a tier alias)."""
    name = model.lower()
    return "claude" in name or any(tier in name for tier in CLAUDE_TIERS)


def suggest_tier_models(
    model: str | None, curated: Sequence[str], *, local: bool = False
) -> dict[str, str]:
    """Coffer's prefill for the Model per tier section.

    - A local runtime, or a connection whose models are not Claude ids: every
      tier is the agent's ``model`` — one loaded model, no second cold load, no
      Claude id sent to an endpoint that does not know it.
    - A gateway serving Claude ids: each tier is the curated model whose name
      carries the tier (``opus``, ``sonnet``, ``haiku``, ``fable``), else the
      ``model``.

    ``fable`` is suggested only when a curated model names it. No ``model``
    means nothing to pin: an empty mapping.
    """
    if not model:
        return {}
    claude_gateway = not local and any(is_claude_model_id(m) for m in curated)
    out: dict[str, str] = {}
    for tier in CLAUDE_TIERS:
        match = next((m for m in curated if tier in m.lower()), None)
        if tier == "fable" and match is None:
            continue
        out[tier] = match if (claude_gateway and match) else model
    return out


__all__ = [
    "CLAUDE_TIERS",
    "is_claude_model_id",
    "suggest_tier_models",
    "tier_env_key",
]

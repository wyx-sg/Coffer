"""What a projection is built from besides the connection: the agent's model
binding and the curated models' recorded facts (spec provider-switching "Take
projected model keys from the agent's binding", "Record a context window and
effort levels with each curated model"). Pure values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

#: Codex compacts at this share of a model's window — Codex's own default,
#: written down because a catalogue entry has to carry the number.
AUTO_COMPACT_SHARE = 0.9


@dataclass(frozen=True)
class ModelBinding:
    """The agent's own choice: model, effort and (Claude Code) the tier pins."""

    model: str | None = None
    effort: str | None = None
    tier_models: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectedModel:
    """One curated text model, with what the connection records about it."""

    id: str
    context_window: int | None = None
    effort_levels: tuple[str, ...] = ()
    default_effort: str | None = None

    @property
    def auto_compact_limit(self) -> int | None:
        if self.context_window is None:
            return None
        return int(self.context_window * AUTO_COMPACT_SHARE)


def find_model(models: Sequence[ProjectedModel], model_id: str | None) -> ProjectedModel | None:
    """The curated entry for ``model_id``, or ``None``."""
    if model_id is None:
        return None
    return next((m for m in models if m.id == model_id), None)


__all__ = ["AUTO_COMPACT_SHARE", "ModelBinding", "ProjectedModel", "find_model"]

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
    """

    model: str | None
    updated_at: datetime
    auto_tidy_enabled: bool = False

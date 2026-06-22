"""The single, global internal-engine model selection (spec 011 amendment
2026-06-22b).

Coffer's own internal LLM engine (memory organizer / reorg / distill /
``coffer__ask``) runs on the connection flagged ``internal_default`` for its
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
    """The one global internal-engine model selection."""

    model: str | None
    updated_at: datetime

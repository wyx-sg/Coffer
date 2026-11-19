"""Coffer's own operating settings: which model transcribes speech (spec
internal-engine "Transcribe speech on its own connection and model")."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class GlobalInternalEngineConfig:
    """The one global set of Coffer's own settings."""

    updated_at: datetime
    #: The speech-to-text model, on the connection marked ``transcribe_default``
    #: (spec internal-engine "Transcribe speech on its own connection and
    #: model"). ``None`` until the operator picks one,
    #: and while it is ``None`` Coffer transcribes nothing.
    transcribe_model: str | None = None

"""MemoryRecord entity for the memory kind."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Actor = Literal["agent", "user"]


@dataclass(frozen=True)
class MemoryRecord:
    """One memory in a store."""

    id: str
    store_name: str
    text: str
    actor: Actor
    created_at: datetime
    updated_at: datetime

"""Per-(skill, agent) binding domain entity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class LinkMode(StrEnum):
    """How a binding's target was realised on disk."""

    SYMLINK = "symlink"
    JUNCTION = "junction"
    COPY_FALLBACK = "copy_fallback"


@dataclass
class BindingState:
    """One row from the `skill_agent_bindings` table."""

    skill_resource_id: int
    agent_resource_id: int
    enabled: bool
    last_linked_at: datetime | None = None
    last_link_path: str | None = None
    link_mode: LinkMode | None = None

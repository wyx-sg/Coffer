"""Pure value objects for transcript distillation (Spec 007 extension)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class TranscriptMessage:
    role: str  # "user" | "assistant" | "system"
    text: str  # already scrubbed; no tool payloads


@dataclass(frozen=True)
class TranscriptSession:
    session_id: str
    agent_type_value: (
        str  # AgentType value; domain.distill must not import domain.agent enum to stay decoupled
    )
    project_path: str | None
    started_at: datetime | None
    messages: tuple[TranscriptMessage, ...] = field(default_factory=tuple)
    source_path: str = ""
    # History-list projection fields (parsed read-only; never persisted).
    title: str | None = None
    last_activity_at: datetime | None = None

    @property
    def message_count(self) -> int:
        return len(self.messages)


@dataclass(frozen=True)
class DistilledInsight:
    name: str
    description: str
    body: str

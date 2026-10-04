"""Wire models for the memory hook and the delivery views
(spec memory "Retrieve the notes a prompt names", "Count what memory delivered
and what was read", "Show what each agent is given at session start")."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HookFireIn(BaseModel):
    """One fire of Coffer's memory hook, as ``coffer memory hook`` relays the
    agent's own hook input."""

    #: The agent whose hook fired, by uid.
    agent_uid: str
    #: ``SessionStart`` or ``UserPromptSubmit``.
    event: str
    session_id: str = ""
    cwd: str = ""
    #: The prompt, for ``UserPromptSubmit``.
    prompt: str = ""


class HookFireOut(BaseModel):
    """What the hook prints: the event's JSON, or nothing when ``output`` is
    null."""

    output: dict[str, Any] | None = None


class AgentDeliveryStatsOut(BaseModel):
    agent_uid: str
    agent_name: str
    agent_type: str
    #: Every audited delivery fire in the window.
    deliveries: int
    #: The same fires by moment: ``session_start``, ``prompt``.
    by_moment: dict[str, int] = Field(default_factory=dict)
    last_delivered_at: datetime | None = None
    #: Distinct notes the agent's sessions opened, from the file paths its tool
    #: calls named; null when that could not be computed.
    notes_read: int | None = None
    #: ``available`` or ``unavailable`` — whether ``notes_read`` was computable.
    notes_read_status: Literal["available", "unavailable"]


class DeliveryOverviewOut(BaseModel):
    window_days: int
    agents: list[AgentDeliveryStatsOut] = Field(default_factory=list)


class DeliveredTextOut(BaseModel):
    agent_uid: str
    agent_name: str
    agent_type: str
    event: str
    #: Exactly what that agent's session-start hook would add; empty when there
    #: is nothing to deliver.
    text: str


class DeliveredOut(BaseModel):
    partition: str
    agents: list[DeliveredTextOut] = Field(default_factory=list)

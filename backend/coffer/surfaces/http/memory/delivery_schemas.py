"""Wire models for the memory hook, memory triggers and the delivery views
(spec memory "Retrieve the notes a prompt names", "Guard a known trap once per
session", "Keep triggers in the vault, armed only by a person", "Count what
memory delivered and what was read", "Show what each agent is given at session
start")."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HookFireIn(BaseModel):
    """One fire of Coffer's memory hook, as ``coffer memory hook`` relays the
    agent's own hook input."""

    #: The agent whose hook fired, by uid.
    agent_uid: str
    #: ``SessionStart``, ``UserPromptSubmit``, ``PreToolUse`` or ``PostToolUse``.
    event: str
    session_id: str = ""
    cwd: str = ""
    #: The prompt, for ``UserPromptSubmit``.
    prompt: str = ""
    #: The tool, for the tool events; only ``Bash`` is acted on.
    tool_name: str = ""
    #: The shell command, for the tool events.
    command: str = ""
    #: What the command printed, for ``PostToolUse``.
    output: str = ""


class HookFireOut(BaseModel):
    """What the hook prints: the event's JSON, or nothing when ``output`` is
    null."""

    output: dict[str, Any] | None = None


class TriggerIn(BaseModel):
    """A trigger a person writes; it is armed by them as it is written."""

    #: ``<partition>/<slug>`` of the note whose substance is the reason.
    note: str
    kind: Literal["block", "context"] = "block"
    #: Regex over each executing shell segment (``program args``).
    command: str = ""
    #: Regex over the whole command; a match keeps the trigger quiet.
    unless: str = ""
    #: Regex over a command's output, for a ``context`` trigger.
    error: str = ""
    #: Shown as the reason when the note itself is gone.
    body: str = ""


class TriggerOut(BaseModel):
    id: str
    note: str
    kind: str
    command: str
    unless: str
    error: str
    #: Whether it takes effect: only a person arms a trigger.
    armed: bool
    armed_by: str
    armed_at: str
    #: ``distil`` for a proposal, empty for one a person wrote.
    proposed_by: str
    created: str
    body: str
    #: The file it lives in.
    path: str


class TriggerListOut(BaseModel):
    triggers: list[TriggerOut] = Field(default_factory=list)


class AgentDeliveryStatsOut(BaseModel):
    agent_uid: str
    agent_name: str
    agent_type: str
    #: Every audited delivery fire in the window.
    deliveries: int
    #: The same fires by moment: ``session_start``, ``prompt``, ``guard``, ``error``.
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

"""Wire models for the memory hook and the delivered view
(spec memory "Retrieve the notes a prompt names", "Show what each agent is given
at session start")."""

from __future__ import annotations

from typing import Any

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

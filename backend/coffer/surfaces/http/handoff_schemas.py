"""The wire shape of a hand-off prompt (``domain/handoff.py``), shared by
every response that hands a chore to an agent."""

from __future__ import annotations

from pydantic import BaseModel


class HandoffOut(BaseModel):
    """A chore for the person's agent. ``prompt`` is the whole text to copy or
    to pre-fill a new conversation with; Coffer never sends it itself."""

    prompt: str


def handoff_out(prompt: str | None) -> HandoffOut | None:
    return HandoffOut(prompt=prompt) if prompt is not None else None


__all__ = ["HandoffOut", "handoff_out"]

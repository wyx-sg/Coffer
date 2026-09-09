"""Message domain entity and ContentBlock value-object union.

A ``ContentBlock`` is one of ``text | tool_use | tool_result | attachment``.
The persistence layer stores ``content`` as a JSON array of block dicts.
The helpers ``block_to_dict`` / ``block_from_dict`` are the single point of
that serialisation logic so the infrastructure layer does not need to know
the block dataclass hierarchy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------


class Role(StrEnum):
    """Message role — matches the SQL ``role`` column values."""

    USER = "user"
    ASSISTANT = "assistant"


# ---------------------------------------------------------------------------
# ContentBlock union
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextBlock:
    """A plain-text segment of a message."""

    text: str
    type: Literal["text"] = "text"


@dataclass(frozen=True)
class ToolUseBlock:
    """A tool invocation requested by the assistant."""

    tool_use_id: str
    tool_name: str
    tool_input: dict[str, Any]  # structurally mutable despite frozen=True — acceptable for v1
    type: Literal["tool_use"] = "tool_use"


@dataclass(frozen=True)
class ToolResultBlock:
    """The result (or error) returned for a prior ``ToolUseBlock``."""

    tool_use_id: str
    tool_name: str
    output: dict[str, Any] | None  # structurally mutable despite frozen=True — acceptable for v1
    error: str | None
    type: Literal["tool_result"] = "tool_result"


@dataclass(frozen=True)
class AttachmentBlock:
    """A reference to a user-supplied file (channel media) — path/mime/filename,
    never the bytes. Persisted in the user message so the attachment survives in
    history, shows in the web Chat page, and is re-materialised for the agent on
    later turns. See ADR-038 / ADR-041 (FR-033)."""

    path: str  # absolute local path in the media dir (NOT emitted to the wire)
    mime: str
    filename: str
    type: Literal["attachment"] = "attachment"


ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock | AttachmentBlock


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def block_to_dict(block: ContentBlock) -> dict[str, Any]:
    """Serialise a ``ContentBlock`` to a plain dict suitable for JSON storage."""
    if isinstance(block, TextBlock):
        return {"type": "text", "text": block.text}
    if isinstance(block, ToolUseBlock):
        return {
            "type": "tool_use",
            "tool_use_id": block.tool_use_id,
            "tool_name": block.tool_name,
            "tool_input": block.tool_input,
        }
    if isinstance(block, ToolResultBlock):
        return {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "tool_name": block.tool_name,
            "output": block.output,
            "error": block.error,
        }
    if isinstance(block, AttachmentBlock):
        return {
            "type": "attachment",
            "path": block.path,
            "mime": block.mime,
            "filename": block.filename,
        }
    # This branch is unreachable given the union, but makes mypy happy.
    raise TypeError(f"unhandled ContentBlock type: {type(block)!r}")  # pragma: no cover


def block_from_dict(data: dict[str, Any]) -> ContentBlock:
    """Deserialise a plain dict (from JSON storage) back to a ``ContentBlock``.

    Raises ``ValueError`` when the ``type`` discriminator is unknown or when a
    known block type is missing a required field.
    """
    block_type = data.get("type")
    try:
        if block_type == "text":
            return TextBlock(text=data["text"])
        if block_type == "tool_use":
            return ToolUseBlock(
                tool_use_id=data["tool_use_id"],
                tool_name=data["tool_name"],
                tool_input=data["tool_input"],
            )
        if block_type == "tool_result":
            return ToolResultBlock(
                tool_use_id=data["tool_use_id"],
                tool_name=data["tool_name"],
                output=data.get("output"),
                error=data.get("error"),
            )
        if block_type == "attachment":
            return AttachmentBlock(
                path=data["path"],
                mime=data["mime"],
                filename=data["filename"],
            )
    except KeyError as exc:
        raise ValueError(
            f"ContentBlock type {block_type!r} is missing required field {exc}"
        ) from exc
    raise ValueError(f"unknown ContentBlock type: {block_type!r}")


# ---------------------------------------------------------------------------
# Message entity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Message:
    """One entry in a conversation.

    ``status`` is ``"complete"`` for user messages and finished assistant
    messages, ``"streaming"`` for an in-flight assistant turn, and ``"failed"``
    for a turn that was interrupted or errored.

    ``model_id``, ``prompt_tokens``, and ``completion_tokens`` are only set
    on assistant messages.
    """

    id: str
    conversation_id: str
    seq: int
    role: Role
    content: list[ContentBlock]  # structurally mutable despite frozen=True — acceptable for v1
    status: Literal["complete", "streaming", "failed"]
    model_id: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    created_at: datetime

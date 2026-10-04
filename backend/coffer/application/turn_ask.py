"""The built-in tool ``coffer__ask`` and the port the gateway serves it through.

Kind-agnostic on purpose: the MCP gateway lists and serves ``coffer__ask`` only
to a session whose requests carry the ``X-Coffer-Turn`` token of a turn Coffer is
running (spec mcp-gateway "Let an agent ask the owner a question during a Coffer
turn"), but it must not import the chat kind that runs turns. The chat kind
satisfies :class:`TurnAskPort`; the composition root hands it to the gateway.
"""

from __future__ import annotations

from typing import Any, Protocol

from coffer.domain.channel_turn import TURN_HEADER, TURN_TOKEN_ENV

ASK_TOOL_NAME = "coffer__ask"

#: What a direct call answers outside a Coffer-run turn.
NOT_IN_TURN_TEXT = (
    "coffer__ask works only inside a Coffer conversation (a turn Coffer runs); "
    "this session is not part of one. Ask the user in your own reply instead."
)

_DESCRIPTION = (
    "Ask the owner a question and wait for the answer. Use it when you need a "
    "decision before you can continue. The turn pauses until the owner answers in "
    "Coffer or in the chat, or stops the task. Give 1 to 4 questions, each with a "
    "short header, the question, and 2 to 4 options (a label and an optional "
    "description); set multi_select to let the owner pick several. The owner can "
    "also type their own answer. Put a summary, a diff or a path the owner needs to "
    "decide in `context` (markdown). Returns the chosen labels and any typed answer "
    "per question."
)

_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "context": {
            "type": "string",
            "description": "Markdown shown above the questions: a summary, a diff, a path.",
        },
        "questions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "header": {"type": "string", "description": "A short label for the question."},
                    "question": {"type": "string", "description": "The question to ask."},
                    "options": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 4,
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["label"],
                        },
                    },
                    "multi_select": {"type": "boolean", "default": False},
                },
                "required": ["header", "question", "options"],
            },
        },
    },
    "required": ["questions"],
}


def ask_tool_descriptor() -> dict[str, Any]:
    """The ``tools/list`` entry of ``coffer__ask``."""
    return {"name": ASK_TOOL_NAME, "description": _DESCRIPTION, "inputSchema": _INPUT_SCHEMA}


class TurnAskPort(Protocol):
    """What the gateway needs from the kind that runs turns."""

    def is_live(self, token: str | None) -> bool:
        """Whether ``token`` names a turn that is running now."""
        ...

    async def ask(self, token: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Raise the question on the turn's conversation and return its result
        once answered, cancelled or expired. A malformed ``arguments`` raises
        ``ValueError`` naming what is wrong."""
        ...


_current: TurnAskPort | None = None


def set_turn_ask(port: TurnAskPort | None) -> None:
    """Called by the composition root with the chat kind's port (``None`` unwires)."""
    global _current
    _current = port


def current_turn_ask() -> TurnAskPort | None:
    """The wired port, or ``None`` when no kind runs turns."""
    return _current


__all__ = [
    "ASK_TOOL_NAME",
    "NOT_IN_TURN_TEXT",
    "TURN_HEADER",
    "TURN_TOKEN_ENV",
    "TurnAskPort",
    "ask_tool_descriptor",
    "current_turn_ask",
    "set_turn_ask",
]

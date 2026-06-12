"""Context-window history trimming helpers for the chat turn orchestrator.

Provides:
- ``_estimate_chars``:  rough char count for a list of Message objects.
- ``_trim_history``:    returns the most-recent messages that fit a char budget.

The heuristic (research.md §8) uses ~4 chars / token; the default budget
leaves 4 k-token headroom below 200 k tokens:
    200_000 tokens x 4 chars/token = 800_000 chars
    800_000 - 64_000 (headroom)   = 736_000 chars
"""

from __future__ import annotations

from typing import Any

from coffer.domain.chat.message import TextBlock, ToolResultBlock, ToolUseBlock

# Context-window budget (chars). Exported so TurnOrchestrator can reference it.
DEFAULT_CHAR_BUDGET: int = 736_000


def estimate_chars(messages: list[Any]) -> int:
    """Rough char count estimate across a list of Message objects."""
    total = 0
    for msg in messages:
        for block in msg.content:
            if isinstance(block, TextBlock):
                total += len(block.text)
            elif isinstance(block, ToolUseBlock):
                total += len(block.tool_name) + len(str(block.tool_input))
            elif isinstance(block, ToolResultBlock):
                total += len(block.tool_name) + len(str(block.output))
    return total


def trim_history(messages: list[Any], char_budget: int) -> tuple[list[Any], bool]:
    """Return the most-recent messages that fit within ``char_budget`` chars.

    Always includes at least the last message (the just-appended user message)
    regardless of size.

    Returns a ``(kept_messages, truncated)`` tuple where ``truncated`` is
    ``True`` when at least one older message was dropped.
    """
    if not messages:
        return [], False

    # Walk backwards accumulating char cost; always keep the last message.
    # Intentional simplification (research.md §8): stop at the first message
    # that would exceed the budget rather than packing maximally — keeps the
    # algorithm O(n) and avoids pathological interleaving of huge messages.
    kept: list[Any] = []
    remaining = char_budget
    for msg in reversed(messages):
        cost = max(1, estimate_chars([msg]))
        if not kept or remaining >= cost:
            kept.append(msg)
            remaining -= cost
        else:
            break  # stop; older messages would push us over budget

    kept.reverse()
    truncated = len(kept) < len(messages)
    return kept, truncated

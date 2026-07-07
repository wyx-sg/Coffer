"""Pure helpers that flatten rich inbound content (forwarded records, fetched
thread/recent history, quoted replies) into readable text folded into a turn
prompt. No platform schema — adapters map their payloads to these shapes first."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = ["ForwardedItem", "flatten_context", "flatten_forwarded", "quote_prefix"]


@dataclass(frozen=True)
class ForwardedItem:
    sender: str
    text: str  # rendered body: text, or "[image] <url>" / "[file] <name>"


def _render(items: Sequence[ForwardedItem], title: str) -> str:
    if not items:
        return ""
    lines = [f"[{title}]"]
    lines += [f"{it.sender or 'unknown'}: {it.text}" for it in items]
    return "\n".join(lines)


def flatten_forwarded(
    items: Sequence[ForwardedItem], *, title: str = "Forwarded chat record"
) -> str:
    return _render(items, title)


def flatten_context(items: Sequence[ForwardedItem], *, title: str) -> str:
    return _render(items, title)


def quote_prefix(sender: str, text: str) -> str:
    return f"> {sender or 'unknown'}: {text}\n"

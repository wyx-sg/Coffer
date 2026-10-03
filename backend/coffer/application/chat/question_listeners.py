"""Who hears a question raised, progressed or closed (the channels' turn renderer
posts and rewrites cards from these). Listeners are synchronous callables
``(conversation_id, block)``; one that raises is logged and skipped."""

from __future__ import annotations

import logging
from collections.abc import Callable

from coffer.domain.chat.question import QuestionBlock

log = logging.getLogger(__name__)

Listener = Callable[[str, QuestionBlock], None]

_RAISED: list[Listener] = []
_PROGRESS: list[Listener] = []
_CLOSED: list[Listener] = []


def _listen(registry: list[Listener], listener: Listener) -> Callable[[], None]:
    registry.append(listener)
    return lambda: registry.remove(listener) if listener in registry else None


def add_raised_listener(listener: Listener) -> Callable[[], None]:
    """Call ``listener(conversation_id, block)`` when a question is raised.
    Returns the function that removes it."""
    return _listen(_RAISED, listener)


def add_progress_listener(listener: Listener) -> Callable[[], None]:
    """Call ``listener`` when one question of a several-question ask is answered
    and the rest still wait."""
    return _listen(_PROGRESS, listener)


def add_closed_listener(listener: Listener) -> Callable[[], None]:
    """Call ``listener`` when a question is answered in full or cancelled, so a
    card can be rewritten."""
    return _listen(_CLOSED, listener)


def _notify(registry: list[Listener], conversation_id: str, block: QuestionBlock) -> None:
    for listener in list(registry):
        try:
            listener(conversation_id, block)
        except Exception:
            log.warning("question listener failed", exc_info=True)


def notify_raised(conversation_id: str, block: QuestionBlock) -> None:
    _notify(_RAISED, conversation_id, block)


def notify_progress(conversation_id: str, block: QuestionBlock) -> None:
    _notify(_PROGRESS, conversation_id, block)


def notify_closed(conversation_id: str, block: QuestionBlock) -> None:
    _notify(_CLOSED, conversation_id, block)


def clear_listeners() -> None:
    """Forget every listener (test teardown only)."""
    _RAISED.clear()
    _PROGRESS.clear()
    _CLOSED.clear()

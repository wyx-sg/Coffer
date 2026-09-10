"""The post-write change hook, kept out of ``KnowledgeService`` itself.

One free function, in its own module for the file-size budget. It exists so the
service can announce a write without the write path inheriting the hook's
failure modes: whatever the composition root installed — today, the trigger
that arms the notes tidy pass — runs after the file is already on disk, so a
hook that raises must never turn a successful write into a failed one.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

_logger = logging.getLogger(__name__)

OnChangeFn = Callable[[str], Awaitable[None]]


async def notify_change(on_change: OnChangeFn | None, scope_name: str) -> None:
    """Run the post-write change hook; a hook failure must never surface."""
    if on_change is None:
        return
    try:
        await on_change(scope_name)
    except Exception:
        # The write succeeded; a post-write hook failure must not surface.
        _logger.warning(
            "knowledge.on_change.hook_failed",
            extra={"store": scope_name},
            exc_info=True,
        )


__all__ = ["OnChangeFn", "notify_change"]

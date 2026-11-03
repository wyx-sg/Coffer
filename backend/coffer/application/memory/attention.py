"""What about memory needs a person (the Overview list): the task notes waiting
to be sorted into knowledge (spec memory "Sort task material into knowledge on
request").

- ``memory_to_sort`` — at least :data:`TO_SORT_THRESHOLD` memories the agents
  filed as task notes wait to be sorted. Coffer starts no agent on its own, so
  this is the reminder; the action opens the Memory page, whose **Sort into
  knowledge** hands the sorting to Claude Code.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from coffer.application.attention import AttentionAction, AttentionItem, Severity

KIND = "memory"
#: How many waiting memories make the reminder worth a person's attention.
TO_SORT_THRESHOLD = 10


class MemoryAttentionSource:
    name = "memory"
    feature: str | None = "memory"

    def __init__(self, to_sort: Callable[[], Awaitable[int]]) -> None:
        self._to_sort = to_sort

    async def items(self) -> Sequence[AttentionItem]:
        waiting = await self._to_sort()
        if waiting < TO_SORT_THRESHOLD:
            return []
        return [
            AttentionItem(
                kind=KIND,
                uid=None,
                title="Memory",
                reason_code="memory_to_sort",
                reason=(
                    f"{waiting} memories your agents filed as task notes wait to be sorted "
                    "into knowledge."
                ),
                severity=Severity.INFO,
                action=AttentionAction(
                    verb="review", method="GET", path="/api/v1/memory/sync/to-sort"
                ),
            )
        ]


__all__ = ["TO_SORT_THRESHOLD", "MemoryAttentionSource"]

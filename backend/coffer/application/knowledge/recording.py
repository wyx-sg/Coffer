"""Record a knowledge write as one commit naming its writer (spec knowledge
"Commit every knowledge write naming its writer").

Every write the service makes goes through here, so the rule
is stated once: open the operation's commit in the vault repository (which
first commits whatever changed under ``knowledge/`` outside Coffer, as a
``disk`` write), touch what it writes, do the write, commit exactly that. The
git calls run off the event loop. With no history wired — a unit test, a
machine with no git — the operation runs unrecorded and nothing else changes.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from coffer.domain.knowledge.entry import ACTOR_AGENT
from coffer.domain.knowledge.history import WRITER_AGENT, WRITER_USER
from coffer.domain.vault.writers import CommitMeta
from coffer.infrastructure.knowledge.history import KnowledgeHistory, Transaction


@contextlib.asynccontextmanager
async def recording(
    history: KnowledgeHistory | None, meta: CommitMeta
) -> AsyncIterator[Transaction]:
    """One operation's commit around the block. The commit is made even when
    the block raises, so a write that half-landed is never left unrecorded."""
    tx = await asyncio.to_thread(history.begin, meta) if history else Transaction(None, meta)
    try:
        yield tx
    finally:
        await asyncio.to_thread(tx.commit)


def writer_of(actor_kind: str) -> str:
    """The history writer for a surface's actor kind (``agent`` or ``user``)."""
    return WRITER_AGENT if actor_kind == ACTOR_AGENT else WRITER_USER


async def settle(history: KnowledgeHistory | None) -> None:
    """Commit what changed under ``knowledge/`` outside Coffer, as ``disk`` writes."""
    if history is not None:
        await asyncio.to_thread(history.settle)


__all__ = ["recording", "settle", "writer_of"]

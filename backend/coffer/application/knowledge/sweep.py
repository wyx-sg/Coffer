"""One tick of the knowledge sweep: the mechanical upkeep a collection needs
without anyone pressing a button.

Four duties, in this order (spec knowledge "Sweep the knowledge root on its
mechanical duties", "Adopt a file dropped into the inbox", "Commit every
knowledge write naming its writer"):

1. **Adopt and promote** every file waiting in a collection's hidden ``.inbox/``
   — one an agent outside Coffer wrote, another machine synced, or an older guide
   told an agent to write — so it becomes a source under ``sources/``.
2. **File loose documents**: a Markdown document outside ``pages/`` and
   ``sources/``, untouched for a minute, moves into ``pages/`` as one
   ``daemon`` commit. Its own edits are committed as ``disk`` first.
3. **Commit edits found on disk** as ``disk`` writes, so a person's own editor or
   an agent's file tools are never attributed to Coffer.
4. **Re-render the guide skill**, because a collection created, renamed or deleted
   changes what every agent must be told. It is cheap and skips a copy that
   already matches.

Nothing here judges content: tidying a collection is the agent's job, started by
the person from the Knowledge page.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from coffer.application.knowledge.intake import adopt_dropped_files, promote_waiting_files
from coffer.application.knowledge.layout import file_loose_documents
from coffer.application.knowledge.recording import settle
from coffer.application.knowledge.service import KnowledgeService

logger = logging.getLogger(__name__)

GuideRefresh = Callable[[], Awaitable[object]]


async def sweep_once(service: KnowledgeService, refresh_guide: GuideRefresh) -> None:
    """Run the four duties; a failing one is logged and never stops the others."""
    try:
        await adopt_dropped_files(service)
        await promote_waiting_files(service)
    except Exception:
        logger.warning("knowledge.sweep.intake_failed", exc_info=True)
    try:
        await file_loose_documents(service)
    except Exception:
        logger.warning("knowledge.sweep.layout_failed", exc_info=True)
    try:
        await settle(service.history)
    except Exception:
        logger.warning("knowledge.sweep.history_failed", exc_info=True)
    try:
        await refresh_guide()
    except Exception:
        logger.warning("knowledge.sweep.guide_failed", exc_info=True)


__all__ = ["GuideRefresh", "sweep_once"]

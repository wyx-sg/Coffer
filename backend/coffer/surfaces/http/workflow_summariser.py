"""The summariser a workflow's context compaction runs on.

Its own module rather than a class in ``workflow_adapters``: it is the only
adapter here that reaches a MODEL, so it carries the internal-connection
plumbing every other internal-LLM consumer in this layer carries, and keeping
that beside the thin bridges would bury it.

``None`` is a first-class answer and the reason this file is so small. With no
internal connection configured there is nothing to summarise WITH, and every
caller degrades by naming what it would have summarised rather than dropping it
(spec workflow FR-047) — so failing here must be cheap and quiet, not fatal.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from coffer.application.engine_ports import LlmCompletionPort, ModelSelectorPort

__all__ = ["LlmSummariser"]

logger = logging.getLogger(__name__)


class LlmSummariser:
    """``SummariserPort`` — one short summary, on the vault's own internal model.

    The same seam the memory layer's organise pass and knowledge ingestion use:
    Coffer's internal-default connection, resolved per call so a connection
    configured after the daemon started is picked up without a restart.

    ``None`` is a first-class answer and the reason this class is so small.
    With no internal connection configured there is nothing to summarise WITH,
    and every caller degrades by naming what it would have summarised rather
    than dropping it — so failing here must be cheap and quiet, not fatal.
    """

    #: Long enough that a summary of a whole task is worth reading, short
    #: enough that five of them fit where one raw transcript did not.
    _MAX_INPUT_CHARS = 60_000

    def __init__(
        self,
        *,
        models: ModelSelectorPort,
        completion: LlmCompletionPort,
        credential_resolver: Callable[[str], str],
    ) -> None:
        self._models = models
        self._completion = completion
        self._credential_resolver = credential_resolver

    async def summarise(self, text: str, *, hint: str) -> str | None:
        try:
            model = await self._models.get_default()
        except Exception:
            logger.warning("workflow.summarise.no_model", exc_info=True)
            return None
        if model is None:
            return None
        try:
            summary: str = await self._completion.complete(
                system=(
                    "You compress a software delivery's history so a later step can act on it. "
                    "Keep decisions, constraints, open questions and anything the developer "
                    "asked for by name. Drop pleasantries, tool chatter and restatement. "
                    "Write prose, no preamble."
                ),
                user=f"{hint}\n\n{text[: self._MAX_INPUT_CHARS]}",
                model=model,
                credential_resolver=self._credential_resolver,
            )
            return summary
        except Exception:
            # A summariser that raises would fail a node that was only trying
            # to open. Degrading to None costs a fuller context, not the turn.
            logger.warning("workflow.summarise.failed", exc_info=True)
            return None

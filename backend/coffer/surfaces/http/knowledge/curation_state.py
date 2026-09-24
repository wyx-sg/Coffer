"""Dependency provider for the curation pass.

Held behind a setter the way the other knowledge-side singletons are, so the
route module does not import the pass directly: curation reaches an LLM
through an injected port, and keeping that wiring in the composition root is
what stops the port leaking into the surface layer. The runner is typed ``Any``
for the same reason — naming ``CurationPass`` here would drag
``application.knowledge.curate`` (and everything it is wired to) into a module
whose whole job is to not know about it.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

_curation_runner: Any | None = None
_vault_lock: asyncio.Lock | None = None


def set_curation_runner(runner: Any) -> None:
    global _curation_runner
    _curation_runner = runner


def get_curation_runner() -> Any:
    if _curation_runner is None:
        raise RuntimeError("curation pass not initialised")
    return _curation_runner


def set_vault_write_lock(lock: asyncio.Lock) -> None:
    """The lock a converge round holds while it rewrites the vault.

    Set from the composition root once sync is wired. The curation pass takes
    it too, because both rewrite vault content and an export caught half-way
    through a rewrite is a torn snapshot git reads as a deliberate change
    (spec knowledge "Never overlap curation with a sync round", spec vault-sync
    "Never overlap a curation pass and a round").
    """
    global _vault_lock
    _vault_lock = lock


@contextlib.asynccontextmanager
async def vault_write_lock() -> AsyncIterator[None]:
    """Hold the vault-write lock, or nothing when sync is not wired.

    A vault with no sync configured has nothing to interleave with, so the
    absence of a lock is the ordinary case rather than a misconfiguration.
    """
    if _vault_lock is None:
        yield
        return
    async with _vault_lock:
        yield

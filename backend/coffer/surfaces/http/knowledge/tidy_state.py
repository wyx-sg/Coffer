"""Dependency provider for the tidy pass.

Held behind a setter the way the other knowledge-side singletons are, so the
route module does not import the pass directly: tidy reaches an LLM through an
injected port, and keeping the wiring in the composition root is what stops
that port leaking into the surface layer.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

_tidy_runner: Any | None = None
_vault_lock: asyncio.Lock | None = None


def set_tidy_runner(runner: Any) -> None:
    global _tidy_runner
    _tidy_runner = runner


def get_tidy_runner() -> Any:
    if _tidy_runner is None:
        raise RuntimeError("tidy runner not initialised")
    return _tidy_runner


def set_vault_write_lock(lock: asyncio.Lock) -> None:
    """The lock a converge round holds while it rewrites the vault.

    Set from the composition root once sync is wired. The tidy pass takes it
    too, because both rewrite vault content and an export caught half-way
    through a rewrite is a torn snapshot git reads as a deliberate change
    (spec vault-sync ``## Unattended rewriters``).
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

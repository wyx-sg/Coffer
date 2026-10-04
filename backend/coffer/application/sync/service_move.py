"""Move the vault out of a synchronised folder (spec vault-sync "Move the
vault out of a synchronised folder").

Rounds take the service's one lock, so holding it for the move is what
pauses them: the
folder is never moved under a half-written commit.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.domain.sync.errors import SyncVaultMoveFailed

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.sync.round_engine import RoundEngine
    from coffer.application.sync.service_ports import VaultMoverPort


@dataclass(frozen=True)
class VaultMove:
    origin: str
    target: str


class MoveMixin:
    """Declares what it borrows from ``SyncService``, which assigns each."""

    _engine: RoundEngine
    _lock: asyncio.Lock
    _mover: VaultMoverPort | None

    async def move_vault(self, to: str) -> VaultMove:
        mover = self._mover
        if mover is None:
            raise SyncVaultMoveFailed("this build cannot move the vault")
        await asyncio.to_thread(mover.check, to)

        def move() -> tuple[str, str]:
            with self._engine.d.lock:
                return mover.move(to)

        async with self._lock:
            origin, target = await asyncio.to_thread(move)
        return VaultMove(origin=origin, target=target)

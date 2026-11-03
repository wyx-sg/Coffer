"""The places each agent's writer writes into, as the Memory page shows them
(spec memory "Write the hub into Codex's memory extension").

Claude Code has one location, its config directory. Codex has one per memory
folder (``memories/``, ``memories_v2/``, and any newer one Coffer cannot write
into yet), each with its own ledger rows and writer status.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from coffer.application.memory.sync_write import LocalAgent, located
from coffer.domain.memory.native_writer import NativeWriter
from coffer.infrastructure.memory.sync_ledger import Ledger

_UNSUPPORTED = {"state": "unsupported", "path": "", "reason": ""}


@dataclass(frozen=True)
class LocationRow:
    """One place the agent's writer writes into."""

    name: str
    path: str
    writer: dict[str, str]
    copies: dict[str, int]


def location_rows(writer: NativeWriter, local: LocalAgent, ledger: Ledger) -> list[LocationRow]:
    rows = []
    for spot in located(writer, local):
        status = writer.status(spot.where)
        rows.append(
            LocationRow(
                name=spot.location_name,
                path=spot.where,
                writer={"state": status.state, "path": status.path, "reason": status.reason},
                copies=dict(Counter(r.state for r in ledger.agent_copies(spot.key).values())),
            )
        )
    return rows


def summed(locations: list[LocationRow]) -> tuple[dict[str, str], dict[str, int]]:
    """The agent's status (the first location that cannot be written, else the
    first location's) and its copies summed over the locations."""
    if not locations:
        return dict(_UNSUPPORTED), {}
    blocked = [loc for loc in locations if loc.writer["state"] != "ok"]
    total: Counter[str] = Counter()
    for loc in locations:
        total.update(loc.copies)
    return (blocked or locations)[0].writer, dict(total)


def agent_copies_everywhere(ledger: Any, local: LocalAgent) -> dict[str, Any]:
    """Every copy the ledger holds for ``local``, in any of its locations."""
    out: dict[str, Any] = {}
    for key, copies in ledger.copies.items():
        if key == local.base_key or key.startswith(f"{local.base_key}#"):
            out.update(copies)
    return out


__all__ = ["LocationRow", "agent_copies_everywhere", "location_rows", "summed"]

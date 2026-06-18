"""Domain types for instructions delivery (spec 004 item 1).

The user keeps one *master instructions* document in Coffer's hub; delivery fans
it out into each agent's instructions file (CLAUDE.md / AGENTS.md / SOUL.md) as a
Coffer-managed block. The block is fenced by the markers below — deliberately
distinct from spec 007's ``coffer:memory`` markers — so the two managed regions
coexist in one file without clobbering each other.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Fences the Coffer-managed instructions block. Distinct from the spec-007
#: memory markers (``coffer:memory:*``) so both blocks coexist in one file.
INSTRUCTIONS_BLOCK_START = "<!-- coffer:instructions:start (managed, do not edit) -->"
INSTRUCTIONS_BLOCK_END = "<!-- coffer:instructions:end -->"


@dataclass(frozen=True)
class MasterInstructions:
    """The hub master-instructions document and a fingerprint of its content.

    ``fingerprint`` is the sha256 of the stored content (``""`` when the master
    has never been written); the caller passes it back on a write for
    optimistic-concurrency (409) stale-write protection.
    """

    content: str
    fingerprint: str


@dataclass(frozen=True)
class InstructionsDeliveryStatus:
    """Derived (never stored) view of one agent's instructions delivery.

    ``delivered`` — the managed block is present in the agent's instructions
    file. ``in_sync`` — the delivered block's body matches the current master.
    """

    delivered: bool
    in_sync: bool

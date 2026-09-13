"""Bind this machine's identity into the one object that evaluates scope.

``scope`` has two axes — the agents a resource is active for and the machines
it is active on (ADR per-agent-resource-scope) — and the machine half is one
fixed fact for the life of the process. Resolving it once here and handing the
resulting evaluator to every consumer is what keeps nine call sites from each
learning about machines, and what keeps the id out of a module-level global a
test would have to fight.
"""

from __future__ import annotations

import asyncio
import pathlib

from coffer.application.scope_evaluator import ScopeEvaluator
from coffer.infrastructure.sync.identity import resolve_identity


async def build_scope_evaluator(root: pathlib.Path | None = None) -> ScopeEvaluator:
    """Resolve this host's machine id and wrap it.

    Through ``resolve_identity`` so the cached value is used when there is one:
    the id is derived from the host either way, and the cache only saves the
    subprocess. Off the event loop regardless, because a cache miss reads the
    operating system — on macOS by running ``ioreg`` — and the daemon's startup
    should not block on that.
    """
    identity = await asyncio.to_thread(resolve_identity, root)
    return ScopeEvaluator(machine_id=identity.machine_id)

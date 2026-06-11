"""Read-path helpers for ``MemoryService`` — fact scans + store metrics.

Extracted from ``service.py`` to keep that file under the project's 400-LOC
ceiling. These free functions own the scan-based queries over a store's
on-disk directory; the service resolves the store first (config + scope) and
delegates the per-directory work here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from pathlib import Path

from coffer.application.memory.service_helpers import du_bytes
from coffer.domain.errors import MemoryNotFound
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.fact import MemoryFact
from coffer.domain.memory.scope import ResolvedScope
from coffer.infrastructure.memory.files import FactFile, scan_store_dir


def read_fact(store_dir: Path, fact_id: str) -> FactFile:
    """Return the ``FactFile`` for ``fact_id`` in ``store_dir`` or raise."""
    scan = scan_store_dir(store_dir)
    ff = scan.files.get(fact_id)
    if ff is None:
        raise MemoryNotFound("memory", fact_id)
    return ff


def list_facts_in_dir(store_dir: Path, *, limit: int, offset: int) -> tuple[list[MemoryFact], int]:
    """Facts in a store, newest-updated first, with the total before paging."""
    files, total = list_fact_files_in_dir(store_dir, limit=limit, offset=offset)
    return [ff.fact for ff in files], total


def list_fact_files_in_dir(
    store_dir: Path, *, limit: int, offset: int
) -> tuple[list[FactFile], int]:
    """Like :func:`list_facts_in_dir` but keeps each fact's on-disk path — one
    directory scan serves the whole page (no per-fact rescans)."""
    scan = scan_store_dir(store_dir)
    files = sorted(
        scan.files.values(),
        key=lambda ff: ff.fact.updated_at,
        reverse=True,
    )
    total = len(files)
    return files[offset : offset + limit], total


def find_fact_store(
    resolved_scopes: Iterable[ResolvedScope],
    fact_id: str,
    store_name_for: Callable[[ResolvedScope], str],
) -> str:
    """Return the store name holding ``fact_id`` across the recall scopes
    (project then global). Raises ``MemoryNotFound`` if absent everywhere."""
    for resolved in resolved_scopes:
        scan = scan_store_dir(resolved.store_dir)
        if fact_id in scan.files:
            return store_name_for(resolved)
    raise MemoryNotFound("memory", fact_id)


async def store_metrics(store_dir: Path, config: MemoryStoreConfig) -> dict[str, object]:
    """Fact count, on-disk byte size, and enabled retrieval modes for a store."""
    scan = scan_store_dir(store_dir)
    disk = await asyncio.to_thread(du_bytes, store_dir) if store_dir.exists() else 0
    return {
        "fact_count": len(scan.files),
        "disk_bytes": disk,
        "enabled_modes": list(config.retrieval_modes),
    }

"""Pure helpers for ``MemoryService``.

Extracted from ``service.py`` to keep that file under the project's 400-LOC
ceiling. These functions have no service state — fact validation, name
derivation, body hashing, on-disk size accounting, and passage/grep→hit
conversion.
"""

from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from coffer.domain.errors import MemoryRejected
from coffer.domain.knowledge.document import Document
from coffer.domain.knowledge.retrieval import GrepHit, MemoryHit, Passage
from coffer.domain.memory.scope import ResolvedScope
from coffer.infrastructure.knowledge.paths import memory_index_path
from coffer.infrastructure.memory.files import read_fact_file


def validate_fact(body: str, max_chars: int) -> None:
    if not body or not body.strip():
        raise MemoryRejected("empty", "fact text is empty")
    if len(body) > max_chars:
        raise MemoryRejected("too_long", f"fact length {len(body)} exceeds store limit {max_chars}")


def derive_name(body: str) -> str:
    for line in body.splitlines():
        if line.strip():
            return line.strip()[:80]
    return "fact"


def body_sha(body: str) -> str:
    return hashlib.sha256(body.strip().encode("utf-8")).hexdigest()


def du_bytes(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            with contextlib.suppress(OSError):
                total += p.stat().st_size
    return total


#: ``fact_id -> documents row`` (recovers the fact's path + updated_at).
GetDocFn = Callable[[str], Awaitable[Document | None]]


async def passages_to_hits(
    passages: Sequence[Passage], resolved: ResolvedScope, get_doc: GetDocFn
) -> list[MemoryHit]:
    """Convert search passages to ``MemoryHit``s with real fact metadata:
    ``time`` is the fact's ``updated_at`` and ``source`` carries the fact
    file's path (per the data-model), both read off the documents row."""
    out: list[MemoryHit] = []
    for p in passages:
        doc = await get_doc(p.document_id)
        source_path = doc.path if doc is not None else p.document_id
        time = doc.updated_at if doc is not None else datetime.now(tz=UTC)
        out.append(
            MemoryHit(
                id=p.document_id,
                text=p.text,
                score=p.score,
                source=f"{resolved.scope.value}:{source_path}",
                time=time,
            )
        )
    return out


def grep_hits_to_memory_hits(hits: Sequence[GrepHit], resolved: ResolvedScope) -> list[MemoryHit]:
    """Convert ripgrep line hits over a store dir to ``MemoryHit``s.

    The matched line is the hit text; the fact id/updated_at come from parsing
    the matched file. ``MEMORY.md`` (the derived index) is skipped, and several
    matches inside one fact dedupe to the first."""
    out: list[MemoryHit] = []
    seen: set[str] = set()
    index_name = memory_index_path()
    for h in hits:
        path = Path(h.path)
        if path.name == index_name:
            continue
        try:
            ff = read_fact_file(path)
        except (OSError, ValueError):
            continue
        if ff.fact.id in seen:
            continue
        seen.add(ff.fact.id)
        out.append(
            MemoryHit(
                id=ff.fact.id,
                text=h.line,
                # Grep has no relevance ranking; a flat score keeps merged
                # cross-store ordering stable.
                score=1.0,
                source=f"{resolved.scope.value}:{path}",
                time=ff.fact.updated_at,
            )
        )
    return out

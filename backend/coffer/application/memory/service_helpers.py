"""Pure helpers for ``MemoryService``.

Extracted from ``service.py`` to keep that file under the project's 400-LOC
ceiling. These functions have no service state — fact validation, name
derivation, body hashing, on-disk size accounting, and passage→hit conversion.
"""

from __future__ import annotations

import contextlib
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from coffer.domain.errors import MemoryRejected
from coffer.domain.knowledge.retrieval import MemoryHit
from coffer.domain.memory.scope import ResolvedScope


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


def to_memory_hits(passages, resolved: ResolvedScope) -> list[MemoryHit]:  # type: ignore[no-untyped-def]
    out: list[MemoryHit] = []
    for p in passages:
        out.append(
            MemoryHit(
                id=p.document_id,
                text=p.text,
                score=p.score,
                source=f"{resolved.scope.value}:{p.document_id}",
                time=datetime.now(tz=UTC),
            )
        )
    return out

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
from coffer.infrastructure.knowledge.paths import journal_dir, knowledge_dir
from coffer.infrastructure.memory.files import read_fact_file
from coffer.infrastructure.memory.journal_files import journal_doc_id


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

    The matched line is the hit text; several matches inside one document dedupe
    to the first.

    ripgrep runs over the whole store dir, so it also reaches content that must
    NEVER surface in recall: the ``handoff/`` / ``rules/`` sibling lanes, the
    ``superseded/`` tombstone, facts abandoned at the store root by a pre-lane
    build, and a leftover legacy ``MEMORY.md``. Recall therefore keeps ONLY hits
    inside the two searchable lanes — the ``knowledge/`` lane (semantic facts) and
    the ``journal/`` lane (episodic events, FR-043) — and skips everything else.
    Knowledge hits are parsed as fact files (id/updated_at from frontmatter);
    journal hits are NOT fact files, so they're keyed per period file."""
    out: list[MemoryHit] = []
    seen: set[str] = set()
    knowledge_root = knowledge_dir(resolved.store_dir).resolve()
    journal_root = journal_dir(resolved.store_dir).resolve()
    for h in hits:
        path = Path(h.path)
        # Resolve so a relative or absolute grep path compares against the
        # absolute lane roots. Anything outside both lanes is recall-excluded.
        hit: MemoryHit | None
        if _is_under(path, journal_root):
            hit = _journal_grep_hit(h, path, resolved)
        elif _is_under(path, knowledge_root):
            hit = _knowledge_grep_hit(h, path, resolved)
        else:
            continue
        if hit is None or hit.id in seen:
            continue
        seen.add(hit.id)
        out.append(hit)
    return out


def _knowledge_grep_hit(h: GrepHit, path: Path, resolved: ResolvedScope) -> MemoryHit | None:
    """A grep hit inside the ``knowledge/`` lane (a per-fact file). ``None`` for
    the lane's ``INDEX.md`` review index or an unparseable file."""
    if path.name == "INDEX.md":  # the lane's human review index is not a fact
        return None
    try:
        ff = read_fact_file(path)
    except (OSError, ValueError):
        return None
    return MemoryHit(
        id=ff.fact.id,
        text=h.line,
        # Grep has no relevance ranking; a flat score keeps merged cross-store
        # ordering stable.
        score=1.0,
        source=f"{resolved.scope.value}:{path}",
        time=ff.fact.updated_at,
    )


def _journal_grep_hit(h: GrepHit, path: Path, resolved: ResolvedScope) -> MemoryHit:
    """A grep hit inside the ``journal/`` lane. Journal files are not fact files,
    so the hit is keyed by ``journal-<period>`` (matching the indexed document id
    so a grep and a keyword hit on the same month dedupe) and timestamped by the
    file mtime rather than parsed frontmatter."""
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        mtime = datetime.now(tz=UTC)
    return MemoryHit(
        id=journal_doc_id(path.stem),
        text=h.line,
        score=1.0,
        source=f"{resolved.scope.value}:{path}",
        time=mtime,
    )


def _is_under(path: Path, root: Path) -> bool:
    """Whether ``path`` lies within ``root`` (both made absolute first).

    Robust to ``path`` arriving absolute or relative as ripgrep returns it, and
    to a non-existent ``path`` (``resolve`` is lexical for missing files)."""
    try:
        return path.resolve().is_relative_to(root)
    except (OSError, ValueError):  # pragma: no cover - defensive
        return False

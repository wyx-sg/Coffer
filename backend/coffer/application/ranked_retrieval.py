"""The kind-agnostic engine behind ``coffer__search`` and ``coffer__recall``.

Both tools do the same thing over a different corpus: keep a disposable
sidecar of section vectors fresh for whatever files are in scope, embed a
query, rank, and fall back to a literal search when there is no embedder
(spec knowledge FR-025..FR-029; spec memory FR-052 names this loop
explicitly and asks for its reuse). Extracting it here is Coffer's own rule
about cross-cutting modules applied to itself: they are pulled out **after**
the second feature needs them, not in anticipation of one — this is that
second feature.

What is genuinely shared, and lives here:

* the disposable-sidecar substrate (``coffer.infrastructure.retrieval.index``)
  and the pure ranking math (``coffer.domain.knowledge.retrieval``) — both
  already documented elsewhere as *substrate*, not knowledge's facade, which
  is what makes reusing them from a kind-agnostic module the intended shape
  rather than a layering violation;
* the control flow: freshen what changed, embed what's stale, rank what's
  present, degrade to literal on any failure.

What is deliberately **not** here, and stays with each kind's own service:

* resolving *which* files are in scope for one call (an agent's visible
  knowledge collections vs. an agent's visible memory partitions) — that
  needs kind-specific concepts (collections, partitions, an agent's Resource
  scope) this module has no business knowing about;
* the literal-search fallback itself — knowledge's is ripgrep over files
  filtered to its collections; memory's is a substring scan over facts
  already loaded in memory (spec memory's own corpus is "hundreds of facts",
  small enough that shelling out is not worth it, and the memory kind may
  not reach into knowledge's ripgrep wrapper regardless — Contract 2b
  confines that substrate exemption to knowledge's own package).

Both of those vary **per call** (an agent's scope can differ call to call),
which is why they arrive as a :class:`Scope` built fresh by the caller for
each ``search``/``rebuild``/``status``, rather than as constructor
dependencies fixed once. What genuinely is fixed per kind — how to read one
file's content, how to get its absolute path for a freshness stamp, and how
to resolve today's embedder — are the three constructor dependencies below.

``resolve`` and ``read_file`` are kept as two separate ports rather than one,
on purpose: :meth:`RankedRetrieval._freshen` calls ``resolve`` for *every*
file in scope on *every* search (a cheap stat + hash, no parsing) to decide
what changed, and calls ``read_file`` — which parses frontmatter — only for
files that turned out stale. Collapsing them into one "read everything"
port would make every search as expensive as a full reindex.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from coffer.domain.knowledge.retrieval import (
    DEFAULT_MIN_SCORE,
    DEFAULT_TOP_K,
    IndexedSection,
    RankedHit,
    rank,
    split_sections,
)
from coffer.infrastructure.retrieval import index

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_MIN_SCORE",
    "DEFAULT_TOP_K",
    "EmbedderFactory",
    "EmbedderPort",
    "Hit",
    "Outcome",
    "RankedRetrieval",
    "ReadFile",
    "ResolveFile",
    "RetrievalMode",
    "RetrievedFile",
    "Scope",
    "Status",
]

#: Lines of the matching section quoted back with a ranked hit — enough to
#: see why it matched, not enough to be a substitute for reading the file.
_EXCERPT_LINES = 4


class EmbedderPort(Protocol):
    """Turns text into vectors. Duplicated from
    ``coffer.application.engine_ports.EmbedderPort`` rather than imported:
    this module reaches into no kind's application package (only the two
    substrate modules named above), and the two Protocols are structurally
    identical, so any real embedder satisfies both with nothing to keep in
    sync. ``embed`` never raises — an empty tuple means "unavailable right
    now", answered by the literal fallback, never an error.
    """

    async def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...


#: Resolved fresh per call: the user may designate an internal connection,
#: or change it, without a restart.
EmbedderFactory = Callable[[], Awaitable[EmbedderPort | None]]

RetrievalMode = Literal["ranked", "literal"]


@dataclass(frozen=True)
class RetrievedFile:
    """One file as ranked retrieval needs to see it: enough to embed it and
    enough to answer a hit with, regardless of what kind of file it is."""

    path: str
    title: str
    description: str
    body: str


#: Absolute path of the file at ``path`` — cheap, no parsing (see the module
#: docstring for why this is not folded into ``ReadFile``).
ResolveFile = Callable[[str], pathlib.Path]

#: Full read: frontmatter parsed into title/description, body extracted.
ReadFile = Callable[[str], RetrievedFile]


@dataclass(frozen=True)
class Hit:
    """One file a search answered with."""

    path: str
    title: str
    description: str
    #: Cosine score in ranked mode; ``None`` when the answer came from the
    #: literal fallback.
    score: float | None
    #: The section heading a ranked hit matched under; empty in literal mode.
    heading: str
    #: The lines worth showing, each ``(line_number, text)``.
    excerpt: tuple[tuple[int, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Outcome:
    """What a search answered, and how."""

    hits: tuple[Hit, ...]
    mode: RetrievalMode
    #: Why the answer is literal rather than ranked; empty in ranked mode.
    reason: str = ""


@dataclass(frozen=True)
class Status:
    """What the sidecar holds right now, for a surface to render honestly."""

    #: False when no internal connection is configured — ranking is off.
    available: bool
    files_indexed: int
    files_total: int
    path: str


#: Every file path in scope for one call, listed however the kind lists it
#: (an agent's visible collections walked on disk; an agent's visible
#: partitions' fact files).
ListPresent = Callable[[], Awaitable[frozenset[str]]]

#: Whether a path the sidecar remembers indexing — but that vanished from the
#: current ``ListPresent`` result — was ever this call's responsibility to
#: prune. Needed because a call's scope is usually a *subset* of the whole
#: namespace (one agent's collections, not every collection that exists):
#: without it, a search scoped to collection A would prune collection B's
#: entries the moment they are merely absent from A's file list.
Owns = Callable[[str], bool]

#: The kind's own degraded answer when ranking cannot run: literal or
#: regex matching, scoped exactly the way the ranked path was scoped.
LiteralFallback = Callable[[str, int, str], Awaitable[Outcome]]


@dataclass(frozen=True)
class Scope:
    """One call's boundary — built fresh by the caller for every
    ``search``/``rebuild``/``status``, because an agent's visible
    collections or partitions can differ call to call. The engine itself
    never resolves an agent's scope; it only ever asks this object for the
    boundary and how to answer within it.
    """

    list_present: ListPresent
    owns: Owns
    literal_fallback: LiteralFallback


class RankedRetrieval:
    """Keeps one namespace's disposable sidecar fresh and answers from it.

    ``namespace`` picks which sidecar file this instance reads and writes
    (``coffer.infrastructure.retrieval.index.index_path``) — the substrate
    that lets two callers (knowledge, memory) share one on-disk root without
    a rebuild of one discarding the other's vectors.
    """

    def __init__(
        self,
        *,
        namespace: str,
        resolve: ResolveFile,
        read_file: ReadFile,
        embedder_factory: EmbedderFactory,
    ) -> None:
        self._namespace = namespace
        self._resolve = resolve
        self._read_file = read_file
        self._embedder_factory = embedder_factory

    # ----- the one public operation ---------------------------------------

    async def search(self, query: str, scope: Scope, *, top_k: int = DEFAULT_TOP_K) -> Outcome:
        present = await scope.list_present()
        if not present or not query.strip():
            return Outcome(hits=(), mode="ranked")

        embedder = await self._embedder_factory()
        if embedder is None:
            return await scope.literal_fallback(query, top_k, "no internal connection")

        sidecar = await self._freshen(present, scope.owns, embedder)
        vectors = await embedder.embed([query])
        if not vectors:
            return await scope.literal_fallback(query, top_k, "embedding unavailable")

        hits = rank(
            vectors[0],
            (s for s in sidecar.sections() if s.path in present),
            top_k=top_k,
            min_score=DEFAULT_MIN_SCORE,
        )
        if not hits:
            return await scope.literal_fallback(query, top_k, "nothing ranked above threshold")
        return Outcome(hits=tuple(self._hit(h) for h in hits), mode="ranked")

    # ----- index maintenance ------------------------------------------------

    async def rebuild(self, scope: Scope) -> Status:
        """Re-embed every file in ``scope`` from scratch, discarding what is
        there — including, as before this extraction, sections for files
        outside ``scope`` (a rebuild is whole-sidecar, not scope-preserving;
        this is inherited behaviour, not a new decision)."""
        present = await scope.list_present()
        embedder = await self._embedder_factory()
        if embedder is None:
            return await self.status(scope)
        sidecar = index.SidecarIndex(namespace=self._namespace)
        await self._embed_into(sidecar, set(present), embedder)
        sidecar.save()
        return await self.status(scope)

    async def status(self, scope: Scope) -> Status:
        present = await scope.list_present()
        sidecar = index.SidecarIndex.load(namespace=self._namespace)
        return Status(
            available=await self._embedder_factory() is not None,
            files_indexed=len(present & sidecar.indexed_paths()),
            files_total=len(present),
            path=str(index.index_path(self._namespace)),
        )

    # ----- internals ---------------------------------------------------------

    async def _freshen(
        self, present: frozenset[str], owns: Owns, embedder: EmbedderPort
    ) -> index.SidecarIndex:
        """Bring the sidecar level with what is on disk, and no further.

        Only files whose freshness stamp changed are re-embedded, so a
        search over an unchanged corpus makes no network call beyond the
        query itself.
        """
        sidecar = index.SidecarIndex.load(namespace=self._namespace)
        stale = {p for p in present if not sidecar.is_fresh(index.stamp_file(p, self._resolve(p)))}
        # Files that vanished are dropped, but only within this call's own
        # scope: a path this call was never responsible for is not ours to
        # prune (see the ``Owns`` docstring).
        gone = {p for p in sidecar.indexed_paths() if p not in present and owns(p)}
        for path in gone:
            sidecar.drop(path)
        if stale:
            await self._embed_into(sidecar, stale, embedder)
        if stale or gone:
            sidecar.save()
        return sidecar

    async def _embed_into(
        self, sidecar: index.SidecarIndex, targets: set[str], embedder: EmbedderPort
    ) -> None:
        for relpath in sorted(targets):
            try:
                entry = self._read_file(relpath)
            except OSError:
                logger.warning(
                    "ranked_retrieval.index.unreadable",
                    extra={"namespace": self._namespace, "path": relpath},
                )
                continue
            sections = split_sections(entry.body)
            if not sections:
                continue
            vectors = await embedder.embed([s.text for s in sections])
            if not vectors:
                # The embedder is down. Leave the rest of the sidecar alone
                # and let this search answer literally; the next one tries
                # again.
                return
            sidecar.replace_file(
                index.stamp_file(relpath, self._resolve(relpath)),
                [
                    IndexedSection(
                        path=relpath,
                        heading=section.heading,
                        start_line=section.start_line,
                        vector=vector,
                    )
                    for section, vector in zip(sections, vectors, strict=False)
                ],
            )

    def _hit(self, hit: RankedHit) -> Hit:
        entry = self._read_file(hit.path)
        lines = entry.body.splitlines()
        start = max(hit.start_line - 1, 0)
        excerpt = tuple(
            (start + offset + 1, text)
            for offset, text in enumerate(lines[start : start + _EXCERPT_LINES])
            if text.strip()
        )
        return Hit(
            path=hit.path,
            title=entry.title,
            description=entry.description,
            score=hit.score,
            heading=hit.heading,
            excerpt=excerpt,
        )

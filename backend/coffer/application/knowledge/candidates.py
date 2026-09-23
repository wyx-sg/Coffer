"""Choosing which documents a piece of new material might belong to.

A curation pass is bounded (spec knowledge FR-023): it sees one piece of
material, at most five existing documents in full, and the collection's whole
catalogue of titles and descriptions. This module answers the middle one.

There is no index and no embedding, so selection is literal: pull the strings a
document about this subject would have to contain — identifiers, headings,
proper nouns — and ask ripgrep which documents contain them. Getting it
wrong is survivable by design, because the catalogue is in the prompt too: a
model handed five irrelevant candidates and a list of every title can still
conclude that none of them is the right home and open a new document. That is
why selection is allowed to be this crude.
"""

from __future__ import annotations

import re

from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.entry import KnowledgeFile
from coffer.infrastructure.knowledge import paths

#: Candidates handed to one pass (FR-023).
DEFAULT_CANDIDATE_LIMIT = 5

#: Terms folded into the one alternation we run. Past this the regex stops
#: discriminating — everything matches something — and starts costing time.
MAX_TERMS = 24

#: Shorter than this and a term matches half the corpus. Latin words need more
#: characters than CJK to carry the same specificity, hence two thresholds.
_MIN_LATIN = 4
_MIN_CJK = 2

#: Spans that tend to be exactly the distinctive thing: code identifiers in
#: backticks, dotted service names, and ALL-CAPS constants.
_BACKTICKED = re.compile(r"`([^`\n]{2,60})`")
_DOTTED = re.compile(r"\b[a-z][a-z0-9_]*(?:[.-][a-z0-9_]+)+\b")
_SHOUTED = re.compile(r"\b[A-Z][A-Z0-9_]{3,}\b")
_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_CJK_RUN = re.compile(r"[一-鿿]{2,8}")
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")

#: Words that appear in every document about anything and so discriminate
#: nothing. Deliberately short: a stopword list that tries to be complete
#: becomes its own maintenance burden, and a useless term costs one alternation
#: branch, not a wrong answer.
_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "been",
        "being",
        "between",
        "does",
        "from",
        "have",
        "into",
        "more",
        "only",
        "other",
        "over",
        "same",
        "such",
        "than",
        "that",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "through",
        "under",
        "what",
        "when",
        "where",
        "which",
        "while",
        "with",
        "would",
        "your",
    }
)


def distinctive_terms(text: str, *, title: str = "") -> tuple[str, ...]:
    """The strings worth asking the corpus about, most specific first.

    Ordered rather than merely collected: the alternation is capped, so what
    gets dropped should be the generic tail, not an identifier.
    """
    ordered: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        term = raw.strip().strip("`*_#.,;:!?()[]{}\"'")
        if not term or len(term) > 60:
            return
        lowered = term.lower()
        if lowered in seen or lowered in _STOPWORDS:
            return
        is_cjk = bool(_CJK_RUN.fullmatch(term))
        if len(term) < (_MIN_CJK if is_cjk else _MIN_LATIN):
            return
        seen.add(lowered)
        ordered.append(term)

    for pattern in (_BACKTICKED, _DOTTED, _SHOUTED):
        for match in pattern.finditer(text):
            add(match.group(1) if pattern is _BACKTICKED else match.group(0))
    for source in (title, *(_HEADING.findall(text))):
        for word in _LATIN_WORD.findall(source):
            add(word)
        for run in _CJK_RUN.findall(source):
            add(run)
    for run in _CJK_RUN.findall(text):
        add(run)
    return tuple(ordered[:MAX_TERMS])


def _alternation(terms: tuple[str, ...]) -> str:
    return "|".join(re.escape(term) for term in terms)


async def select(
    service: KnowledgeService,
    collection: str,
    source: KnowledgeFile,
    *,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> tuple[str, ...]:
    """Documents most likely to be this material's home, best first.

    When the material IS a document — the sweep came back for one a person
    edited — that document is never its own candidate: it is already in front
    of the pass in full.

    Empty is a legitimate answer and means "nothing in the corpus mentions any
    of this" — for a genuinely new subject that is the truth, and the pass goes
    on to create a document rather than forcing the material into a document it
    does not belong in.
    """
    terms = distinctive_terms(source.body, title=source.title)
    if not terms:
        return ()
    outcome = await service.match_documents(_alternation(terms), collection=collection)
    hits: dict[str, int] = {}
    for match in outcome.matches:
        if match.path == source.path or match.path.rsplit("/", 1)[-1] == paths.README_NAME:
            continue
        hits[match.path] = hits.get(match.path, 0) + 1
    ranked = sorted(hits.items(), key=lambda item: (-item[1], item[0]))
    return tuple(path for path, _ in ranked[:limit])


__all__ = ["DEFAULT_CANDIDATE_LIMIT", "MAX_TERMS", "distinctive_terms", "select"]

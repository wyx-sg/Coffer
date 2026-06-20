"""Prompt builder + JSON parser for the memory organizer's one-shot merge.

Clones the distillation prompt pattern (``application/distill/prompt.py``):
manual structured output — strip ``` fences, ``json.loads``, validate keys —
never ``with_structured_output``. A malformed response parses to ``None`` so the
organizer SKIPS the item (leaves it in the inbox) rather than writing or
corrupting a topic doc.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from coffer.infrastructure.memory.topic_files import TopicDoc

logger = logging.getLogger(__name__)

#: A candidate topic doc presented to the LLM is capped so a few large docs can't
#: blow the context window on the merge call.
_MAX_CANDIDATE_CHARS = 6_000
#: ``_SAFE_SEGMENT`` from ``infrastructure.knowledge.paths`` — a returned slug must
#: be a single safe path segment or the item is skipped (never written).
_SAFE_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_DOTS_ONLY_RE = re.compile(r"^\.+$")

ORGANIZER_SYSTEM = """\
You are Coffer's memory organizer. You maintain a small set of coherent topic \
documents out of raw remembered notes.

You are given ONE new note and zero or more CANDIDATE existing topic documents. \
Either MERGE the note into the single best-fitting candidate — preserving ALL of \
that document's existing content and any human edits, integrating the new \
information, and removing only exact duplicates — or CREATE a new topic when none \
of the candidates fits.

Rules:
- NEVER delete information. Keep the result concise and well-structured with \
Markdown headings.
- When merging, return the FULL updated document body (the existing content plus \
the integration), not just the new part.
- When creating, invent a short kebab-case topic_slug.

Return ONLY a JSON object with these exact string fields:
  topic_slug        — kebab-case slug (e.g. "deploy-conventions")
  topic_title       — short human-readable title
  topic_description — one-line summary
  markdown          — the FULL topic document body (Markdown)

Return ONLY the JSON object — no prose before or after.
"""

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass(frozen=True)
class OrganizedTopic:
    """The validated payload of one organizer LLM call."""

    topic_slug: str
    topic_title: str
    topic_description: str
    markdown: str


def build_user_prompt(*, item_body: str, candidates: list[TopicDoc]) -> str:
    """Render the USER message: the new note + each candidate topic doc."""
    parts = [f"NEW note:\n\n{item_body.strip()}\n"]
    if candidates:
        parts.append("CANDIDATE existing topic documents:\n")
        for doc in candidates:
            body = doc.body.strip()
            if len(body) > _MAX_CANDIDATE_CHARS:
                body = body[:_MAX_CANDIDATE_CHARS] + "\n…[truncated]"
            parts.append(f"### {doc.slug} — {doc.title}\n{body}\n")
    else:
        parts.append("There are no existing topic documents yet. Create a new topic.\n")
    parts.append(
        "Merge the NEW note into the best-fitting candidate, or invent a new "
        "topic_slug if none fits."
    )
    return "\n".join(parts)


def parse_organized_topic(raw: str) -> OrganizedTopic | None:
    """Parse the LLM response into a validated ``OrganizedTopic``.

    Returns ``None`` on ANY failure — non-JSON, not an object, a missing/empty
    required key, or a ``topic_slug`` that is not a safe single path segment — so
    the organizer skips the item (it stays in the inbox; no doc is written)."""
    text = raw.strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.debug("organizer: could not parse JSON from LLM response")
        return None
    if not isinstance(data, dict):
        logger.debug("organizer: expected a JSON object, got %s", type(data).__name__)
        return None

    try:
        # Normalize to lowercase: slugs are filenames, so a case variant (e.g.
        # "Realm" vs an on-disk "realm.md") must not be treated as a different
        # topic — on a case-insensitive filesystem that would split one topic into
        # two docs. The prompt already asks for lowercase kebab-case.
        slug = str(data["topic_slug"]).strip().lower()
        title = str(data["topic_title"]).strip()
        description = str(data["topic_description"]).strip()
        markdown = str(data["markdown"]).strip()
    except KeyError:
        logger.debug("organizer: response missing a required key: %r", data)
        return None

    if not (slug and title and description and markdown):
        logger.debug("organizer: response has an empty required field")
        return None
    if _DOTS_ONLY_RE.fullmatch(slug) or not _SAFE_SLUG_RE.fullmatch(slug):
        logger.debug("organizer: unsafe topic_slug %r — skipping item", slug)
        return None

    return OrganizedTopic(
        topic_slug=slug,
        topic_title=title,
        topic_description=description,
        markdown=markdown,
    )

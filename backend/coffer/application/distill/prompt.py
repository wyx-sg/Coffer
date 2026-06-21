"""Prompt builder and insight JSON parser for transcript distillation."""

from __future__ import annotations

import json
import logging
import re

from coffer.domain.distill.session import DistilledInsight, TranscriptSession

logger = logging.getLogger(__name__)

_MAX_USER_CHARS = 12_000  # cap conversation text sent to LLM

_SYSTEM = """\
You are a knowledge-distillation assistant. Your task is to read a software engineering \
conversation between a developer and a coding agent and extract DURABLE, project-relevant insights.

An insight is DURABLE when it is the kind of thing a future engineer would want to know — \
typically one of:
- A decision: an architectural or design decision made, including the rationale.
- A gotcha: a failed approach, surprising bug, or hard-won lesson worth remembering.
- A convention: a naming convention, style rule, or project standard that was established.
- A todo: an open action item or deferred decision explicitly noted in the conversation.

Rules:
- IGNORE transient chatter, exploratory thinking, trivial steps, and status updates.
- Do NOT invent or infer anything not explicitly stated in the conversation.
- If there are no durable insights, return an empty JSON array.

Return ONLY a JSON array of objects with these exact fields:
  name        — short title (≤ 80 chars)
  description — one-sentence summary (≤ 200 chars)
  body        — full detail (Markdown, ≤ 1000 chars)

Example (valid response):
[
  {
    "name": "Use ULIDs for all entity IDs",
    "description": "Project convention established in session.",
    "body": "All database entities use ULIDs (not UUIDs) for primary keys."
  }
]

Return ONLY the JSON array — no prose before or after.
"""

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def build_prompt(session: TranscriptSession) -> tuple[str, str]:
    """Return (system, user) prompt strings for distilling *session*."""
    lines: list[str] = []
    for msg in session.messages:
        role_label = msg.role.capitalize()
        lines.append(f"{role_label}: {msg.text}")

    conversation = "\n".join(lines)
    if len(conversation) > _MAX_USER_CHARS:
        conversation = conversation[:_MAX_USER_CHARS] + "\n…[truncated]"

    project_hint = f"Project path: {session.project_path}\n\n" if session.project_path else ""
    user = f"{project_hint}Conversation:\n\n{conversation}"
    return _SYSTEM, user


def parse_insights(raw: str) -> list[DistilledInsight]:
    """Parse LLM response *raw* into a list of DistilledInsight.

    Strips ``` fences, loads JSON, maps to domain objects.
    Returns [] on any parse failure or if input is not valid JSON array.
    Skips items missing required fields.
    """
    text = raw.strip()

    # Strip code fences if present
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.debug("parse_insights: could not parse JSON from LLM response")
        return []

    if not isinstance(data, list):
        logger.debug("parse_insights: expected JSON array, got %s", type(data).__name__)
        return []

    results: list[DistilledInsight] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            insight = DistilledInsight(
                name=item["name"],
                description=item["description"],
                body=item["body"],
            )
        except (KeyError, TypeError):
            logger.debug("parse_insights: skipping item with missing fields: %r", item)
            continue
        results.append(insight)

    return results

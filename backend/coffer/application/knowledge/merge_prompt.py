"""Prompt builder + JSON parser for the same-project merge-scan verdict.

Clones the organizer prompt pattern (``organizer_prompt.py``): manual
structured output — strip ``` fences, ``json.loads``, validate keys — never
``with_structured_output``. A malformed response parses to ``None`` so the
scan SKIPS the pair (no proposal) rather than guessing (FR-056).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Cap on the fact-title / topic-slug samples sent per store so a large store
#: cannot blow the context window of the one-shot judgment call.
MAX_SAMPLE_TITLES = 15
MAX_SAMPLE_SLUGS = 10

MERGE_JUDGE_SYSTEM = """\
You are Coffer's memory-store auditor. Coffer keeps one memory store per
software project, but multi-machine sync and identity changes can leave TWO
stores that really describe the SAME project (same repository checked out at
different paths or machines, a renamed remote, a fork).

You are given the evidence for two stores: display label, recorded project
root path, normalized git remote (when known), fact count, and samples of
fact titles and topic slugs. Decide whether they describe the same project.

Be conservative: two stores that merely use the same language or framework
are NOT the same project. Strong signals are matching repository/directory
names, matching remotes, and fact titles that reference the same components,
commands, or people.

Return ONLY a JSON object with these exact fields:
  same_project — boolean
  confidence   — "high" | "medium" | "low"
  reason       — one short sentence justifying the verdict

Return ONLY the JSON object — no prose before or after.
"""

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_CONFIDENCES = frozenset({"high", "medium", "low"})


@dataclass(frozen=True)
class StoreEvidence:
    """What the scan knows about one store (FR-056) — also the wire shape."""

    store: str
    label: str | None
    root: str | None
    remote: str | None
    facts: int
    fact_titles: list[str]
    topic_slugs: list[str]

    def as_prompt_dict(self) -> dict[str, object]:
        return {
            "store": self.store,
            "label": self.label,
            "project_root": self.root,
            "normalized_remote": self.remote,
            "fact_count": self.facts,
            "fact_title_sample": self.fact_titles[:MAX_SAMPLE_TITLES],
            "topic_slug_sample": self.topic_slugs[:MAX_SAMPLE_SLUGS],
        }


@dataclass(frozen=True)
class MergeVerdict:
    """The validated payload of one merge-judgment LLM call."""

    same_project: bool
    confidence: str
    reason: str


def build_pair_prompt(a: StoreEvidence, b: StoreEvidence) -> str:
    """Render the USER message: the two stores' evidence, side by side."""
    payload = {"store_a": a.as_prompt_dict(), "store_b": b.as_prompt_dict()}
    return "Are these two memory stores the same project?\n\n" + json.dumps(
        payload, ensure_ascii=False, indent=2
    )


def parse_verdict(raw: str) -> MergeVerdict | None:
    """Parse the LLM response; ``None`` (skip the pair) on any shape problem."""
    text = raw.strip()
    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("merge_scan.verdict.unparseable")
        return None
    if not isinstance(data, dict):
        return None
    same = data.get("same_project")
    confidence = data.get("confidence")
    reason = data.get("reason")
    if not isinstance(same, bool):
        return None
    if not isinstance(confidence, str) or confidence not in _CONFIDENCES:
        return None
    if not isinstance(reason, str) or not reason.strip():
        return None
    return MergeVerdict(same_project=same, confidence=confidence, reason=reason.strip())

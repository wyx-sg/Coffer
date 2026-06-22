"""Autonomous rules-lane split (spec 007 amendment 2026-06-22).

When a rules file in the ``rules/`` lane grows past a threshold, the lane splits
itself by topic: an injected classifier assigns each rule a short category slug,
the rules are rewritten into per-category ``rules/<slug>.md`` files (merging into
any existing one), and the oversized source file is removed. Applied uniformly
and recursively — a category file that itself exceeds the threshold is
re-classified into finer slugs — so the lane stays navigable as it grows.

The classifier (an LLM call) and the changelog writer are injected; this module
is pure orchestration over the ``rules_files`` I/O helpers (no LLM / infra-chat
import, honouring the application-layer dependency contract).
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path

from coffer.application.memory.organizer_ports import LlmCompletionPort
from coffer.domain.provider.config import ProviderConfig
from coffer.infrastructure.knowledge.paths import rule_file_path, rules_dir
from coffer.infrastructure.memory.rules_files import (
    count_rules,
    rule_bullets,
    write_rules_file,
)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

RULES_SPLIT_SYSTEM = (
    "You organise a list of behavioural rules into a few coherent topic "
    "categories. Group related rules under the same short, lowercase, hyphenated "
    "category slug (e.g. 'git', 'testing', 'pull-requests'). Use as FEW categories "
    "as the rules naturally fall into, but never lump distinct topics into one "
    "category. Reply with ONLY a JSON object of the form "
    '{"assignments": [{"index": <int>, "category": "<slug>"}, ...]} — exactly one '
    "entry per input rule, referenced by its index."
)

#: A rules file beyond this many rules splits itself by topic (per the amendment).
RULES_SPLIT_THRESHOLD = 100

#: Recursion bound — the maximum depth of nested sub-splits in one run. Also the
#: backstop against a classifier that never reduces a file below the threshold.
_MAX_PASSES = 8

#: ``rules -> {rule_text: category_slug}`` — the (LLM-backed) classifier.
ClassifyFn = Callable[[list[str]], Awaitable[dict[str, str]]]
#: ``message -> None`` — an optional changelog/audit sink for each split.
LogFn = Callable[[str], Awaitable[None]]


def _slugify(value: str) -> str:
    """Normalise a classifier-chosen category into one safe path segment."""
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return slug or "general"


def build_split_user(rules: list[str]) -> str:
    """The user prompt: the rules to categorise, one per line, by index."""
    lines = ["Rules to categorise (one per line, by index):", ""]
    lines.extend(f"{i}. {rule}" for i, rule in enumerate(rules))
    return "\n".join(lines)


def parse_classification(raw: str, rules: list[str]) -> dict[str, str]:
    """Parse the LLM's ``{"assignments": [{"index", "category"}, ...]}`` into a
    ``{rule_text: category}`` map. Tolerant: code fences stripped, malformed JSON
    or out-of-range/incomplete entries are dropped (→ an empty map, which makes
    the split a safe no-op rather than a crash)."""
    text = raw.strip()
    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    assignments = data.get("assignments") if isinstance(data, dict) else None
    if not isinstance(assignments, list):
        return {}
    out: dict[str, str] = {}
    for entry in assignments:
        if not isinstance(entry, dict):
            continue
        idx, cat = entry.get("index"), entry.get("category")
        if isinstance(idx, int) and isinstance(cat, str) and cat.strip() and 0 <= idx < len(rules):
            out[rules[idx]] = cat.strip()
    return out


async def run_rules_split(
    store_dir: Path,
    *,
    llm: LlmCompletionPort,
    model: ProviderConfig,
    credential_resolver: Callable[[str], str],
    threshold: int = RULES_SPLIT_THRESHOLD,
    log: LogFn | None = None,
) -> int:
    """Split oversized rule files, classifying each via a one-shot LLM call.

    The thin entry point the organizer calls: it wraps ``llm.complete`` into a
    ``ClassifyFn`` and delegates to :func:`split_oversized_rules`."""

    async def _classify(rules: list[str]) -> dict[str, str]:
        raw = await llm.complete(
            system=RULES_SPLIT_SYSTEM,
            user=build_split_user(rules),
            model=model,
            credential_resolver=credential_resolver,
        )
        return parse_classification(raw, rules)

    return await split_oversized_rules(store_dir, threshold=threshold, classify=_classify, log=log)


async def split_oversized_rules(
    store_dir: Path,
    *,
    threshold: int = RULES_SPLIT_THRESHOLD,
    classify: ClassifyFn,
    log: LogFn | None = None,
) -> int:
    """Split every over-threshold ``rules/*.md`` file into per-category files.

    Returns the number of category-file writes performed (``0`` when nothing is
    over threshold). Recurses into the files it writes so a still-oversized
    category re-splits into finer slugs, bounded by ``_MAX_PASSES``. A file the
    classifier maps to a single category cannot be reduced and is left as-is.
    """
    rdir = rules_dir(store_dir)
    if not rdir.exists():
        return 0
    writes = 0
    unsplittable: set[str] = set()
    for _ in range(_MAX_PASSES):
        oversized = [
            p
            for p in sorted(rdir.glob("*.md"))
            if p.stem not in unsplittable and count_rules(p.read_text(encoding="utf-8")) > threshold
        ]
        if not oversized:
            break
        for path in oversized:
            rules = rule_bullets(path.read_text(encoding="utf-8"))
            mapping = await classify(rules)
            groups: dict[str, list[str]] = {}
            for rule in rules:
                groups.setdefault(_slugify(mapping.get(rule) or "general"), []).append(rule)
            if len(groups) <= 1:
                unsplittable.add(path.stem)  # one category for all → cannot reduce
                continue
            for slug, group_rules in groups.items():
                target = rule_file_path(store_dir, slug)
                existing = (
                    rule_bullets(target.read_text(encoding="utf-8")) if target.exists() else []
                )
                write_rules_file(target, existing + group_rules)
                writes += 1
            if path.stem not in groups:
                path.unlink()  # source fully redistributed
            if log is not None:
                await log(f"split rules '{path.stem}' → {', '.join(sorted(groups))}")
    return writes


__all__ = [
    "RULES_SPLIT_SYSTEM",
    "RULES_SPLIT_THRESHOLD",
    "ClassifyFn",
    "LogFn",
    "build_split_user",
    "parse_classification",
    "run_rules_split",
    "split_oversized_rules",
]

"""On-disk rules lane: ``rules/rules.md`` plus per-category ``rules/<slug>.md``.

Plain-markdown (no frontmatter): a ``# Rules`` header + one ``- `` bullet per
rule. New rules append to ``rules.md``; once it grows past a threshold the
autonomous split (spec 007 amendment 2026-06-22) redistributes rules into
per-topic ``rules/<slug>.md`` files. ``read_all_rules`` concatenates every file
in the lane for injection. Idempotent on exact-duplicate bullet text; atomic
writes via ``infrastructure.knowledge.fs.atomic_write_text`` so a crash never
leaves a partial file. No LLM here — pure file I/O.
"""

from __future__ import annotations

from pathlib import Path

from coffer.infrastructure.knowledge.fs import atomic_write_text


def rule_bullets(text: str) -> list[str]:
    """The rule texts in ``text`` — the content of each ``- ``/``* `` bullet line
    (marker and surrounding whitespace stripped); non-bullet lines are ignored."""
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            out.append(stripped[2:].strip())
    return out


def count_rules(text: str) -> int:
    """Number of rule bullets in ``text`` (the split threshold is measured here)."""
    return len(rule_bullets(text))


def _render_rules(rules: list[str]) -> str:
    """A ``# Rules`` document body for ``rules`` — exact-duplicate bullets dropped,
    first-seen order preserved."""
    seen: set[str] = set()
    lines = ["# Rules"]
    for rule in rules:
        rule = rule.strip()
        if not rule or rule in seen:
            continue
        seen.add(rule)
        lines.append(f"- {rule}")
    return "\n".join(lines) + "\n"


def write_rules_file(path: Path, rules: list[str]) -> None:
    """(Over)write ``path`` with a ``# Rules`` doc of ``rules`` (dedup, atomic)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, _render_rules(rules))


def read_all_rules(rules_dir: Path) -> str | None:
    """Concatenate every ``rules/*.md`` file (sorted by name) into one markdown
    string for injection, or ``None`` when the lane has no rules. Naturally covers
    the legacy single ``rules.md`` (it is just one of the globbed files)."""
    if not rules_dir.exists():
        return None
    parts: list[str] = []
    for path in sorted(rules_dir.glob("*.md")):
        body = path.read_text(encoding="utf-8").strip("\n")
        if body:
            parts.append(body)
    return "\n\n".join(parts) or None


def read_rules(path: Path) -> str | None:
    """Read the rules file, returning ``None`` if it does not exist."""
    try:
        return path.read_text(encoding="utf-8").strip("\n") or None
    except OSError:
        return None


def append_rule(path: Path, rule: str) -> bool:
    """Append a rule as a bullet under a stable ``# Rules`` header.

    Idempotent on the exact rule text — does not duplicate bullets. Returns
    ``True`` if the rule was appended, ``False`` if it was already present (a
    no-op). The whole file is written atomically so a crash never corrupts it.
    """
    rule = rule.strip()
    if not rule:
        return False
    existing = read_rules(path) or ""
    # Already a bullet → keep as-is; anything else (incl. a leading "#" that
    # would otherwise render as a heading and break the list) becomes a bullet.
    bullet = rule if rule.startswith(("-", "*")) else f"- {rule}"
    if bullet in existing.splitlines():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "# Rules\n" if not existing else existing.rstrip("\n") + "\n"
    atomic_write_text(path, header + bullet + "\n")
    return True

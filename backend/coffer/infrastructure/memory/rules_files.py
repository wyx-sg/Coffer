"""On-disk rules lane: a single ``rules/rules.md`` per memory store.

Plain-markdown append (no frontmatter): a ``# Rules`` header + one ``- `` bullet
per rule. Idempotent on exact-duplicate bullet text. Atomic write via
``infrastructure.knowledge.fs.atomic_write_text`` so a crash never leaves a
partial file. No LLM — only the organizer's existing per-item call classifies
an item as a rule; this module handles pure file I/O.
"""

from __future__ import annotations

from pathlib import Path

from coffer.infrastructure.knowledge.fs import atomic_write_text


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

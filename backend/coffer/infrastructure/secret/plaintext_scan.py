"""The secret references skill files cite, and which skill files are read.

``skills_citing_secrets`` is a literal search of the skill master store for
``coffer://secret/<name>`` references. Plaintext secrets themselves are found
by ``detector`` (spec secret "Detect plaintext secrets with the bundled rules").
"""

from __future__ import annotations

import pathlib

from coffer.domain.secrets import cited_secret_names

SKILL_SUFFIXES = {".md", ".sh", ".py", ".env", ".json", ".yaml", ".yml", ".toml", ".txt"}
MAX_BYTES = 1_000_000


def skills_citing_secrets(skills_root: pathlib.Path) -> dict[str, set[str]]:
    """``{secret name: {skill, …}}`` for every ``coffer://secret/<name>`` a skill's
    files mention — a literal search of Coffer's own skill master store."""
    out: dict[str, set[str]] = {}
    if not skills_root.is_dir():
        return out
    for path in skills_root.rglob("*"):
        rel = path.relative_to(skills_root)
        if (
            not path.is_file()
            or path.suffix not in SKILL_SUFFIXES
            or any(part.startswith(".") for part in rel.parts)
            or path.stat().st_size > MAX_BYTES
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name in cited_secret_names(text):
            out.setdefault(name, set()).add(rel.parts[0])
    return out


def skill_citations(
    skills_root: pathlib.Path, only: str | None = None
) -> dict[str, dict[str, list[str]]]:
    """``{skill: {uri name: [relative paths]}}`` for every file of the skill master
    store (or of the skill ``only``) holding ``coffer://secret/<name>`` — the
    citation index's reading of the files."""
    out: dict[str, dict[str, list[str]]] = {}
    if not skills_root.is_dir():
        return out
    base = skills_root / only if only else skills_root
    if not base.is_dir():
        return out
    for path in base.rglob("*"):
        rel = path.relative_to(skills_root)
        if (
            not path.is_file()
            or path.suffix not in SKILL_SUFFIXES
            or any(part.startswith(".") for part in rel.parts)
            or path.stat().st_size > MAX_BYTES
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name in cited_secret_names(text):
            paths = out.setdefault(rel.parts[0], {}).setdefault(name, [])
            paths.append(str(pathlib.PurePosixPath(*rel.parts[1:])))
    return out

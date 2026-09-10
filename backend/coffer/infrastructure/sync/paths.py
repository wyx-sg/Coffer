"""Export/import path resolution (spec vault-export-import).

An export mirrors the file-backed trees (knowledge, skills). Their
roots are resolved here — not imported from the kind modules — so the sync
slice stays decoupled from every kind (cross-kind import fence) while
honouring the same ``$COFFER_*_ROOT`` overrides the kinds use.
"""

from __future__ import annotations

import os
import pathlib


def _expand_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME", "~")).expanduser()


def _rooted(env_var: str, *segments: str) -> pathlib.Path:
    override = os.environ.get(env_var)
    if override:
        return pathlib.Path(override).expanduser()
    return _expand_home().joinpath(".coffer", *segments)


def knowledge_root() -> pathlib.Path:
    """``~/.coffer/knowledge/`` (override ``$COFFER_KNOWLEDGE_ROOT``)."""
    return _rooted("COFFER_KNOWLEDGE_ROOT", "knowledge")


def skills_root() -> pathlib.Path:
    """``~/.coffer/skills/`` — the canonical skill master store."""
    return _rooted("COFFER_SKILLS_ROOT", "skills")


#: The file-backed trees an export mirrors, as (bundle-subdir, live-root) pairs.
def mirrored_trees() -> list[tuple[str, pathlib.Path]]:
    return [
        ("knowledge", knowledge_root()),
        ("skills", skills_root()),
    ]

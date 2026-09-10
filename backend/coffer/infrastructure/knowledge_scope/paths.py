"""Scope-facing view of the on-disk knowledge layout.

The substrate owns path construction in ``infrastructure/knowledge/paths.py``;
this module re-exports the lane helpers the scope adapters use, so a caller
reading the notes-lane code does not have to reach across into the engine
package. Keep new path logic in the substrate.
"""

from __future__ import annotations

from coffer.infrastructure.knowledge.paths import (
    fact_path,
    history_dir,
    history_path,
    knowledge_root,
    note_path,
    notes_dir,
    scope_dir,
)

__all__ = [
    "fact_path",
    "history_dir",
    "history_path",
    "knowledge_root",
    "note_path",
    "notes_dir",
    "scope_dir",
]

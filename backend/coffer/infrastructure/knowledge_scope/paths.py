"""Scope-facing view of the on-disk knowledge layout.

The substrate owns path construction in ``infrastructure/knowledge/paths.py``;
this module re-exports the lane helpers the scope adapters use, so a caller
reading the entry-lane code does not have to reach across into the engine
package. Keep new path logic in the substrate.
"""

from __future__ import annotations

from coffer.infrastructure.knowledge.paths import (
    fact_path,
    handoff_dir,
    handoff_path,
    inbox_dir,
    inbox_item_path,
    knowledge_dir,
    knowledge_root,
    rules_dir,
    rules_path,
    scope_dir,
    superseded_dir,
    topic_path,
)

__all__ = [
    "fact_path",
    "handoff_dir",
    "handoff_path",
    "inbox_dir",
    "inbox_item_path",
    "knowledge_dir",
    "knowledge_root",
    "rules_dir",
    "rules_path",
    "scope_dir",
    "superseded_dir",
    "topic_path",
]

"""On-disk memory layout (spec 007).

The substrate owns path construction in ``infrastructure/knowledge/paths.py``;
the data-model documents the memory paths under this module, so it re-exports
the memory helpers from the shared owner. Keep new path logic in the substrate.
"""

from __future__ import annotations

from coffer.infrastructure.knowledge.paths import (
    fact_path,
    inbox_dir,
    inbox_item_path,
    knowledge_dir,
    memory_global_dir,
    memory_project_dir,
    memory_projects_dir,
    memory_root,
    memory_store_dir,
)

__all__ = [
    "fact_path",
    "inbox_dir",
    "inbox_item_path",
    "knowledge_dir",
    "memory_global_dir",
    "memory_project_dir",
    "memory_projects_dir",
    "memory_root",
    "memory_store_dir",
]

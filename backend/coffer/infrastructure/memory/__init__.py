"""Infrastructure adapters for the memory kind (spec 007 redesign).

No mem0, no chroma. The index/retrieval engine lives in the shared substrate
``coffer.infrastructure.knowledge``; this package keeps only the memory-specific
on-disk concerns (paths here; per-fact file read/write + ``MEMORY.md`` render +
dir-delta scan are added by the application phase in ``files.py``).
"""

from __future__ import annotations

from coffer.infrastructure.memory.files import (
    delete_fact_file,
    read_fact_file,
    regenerate_memory_index,
    render_fact_markdown,
    scan_store_dir,
    write_fact_file,
)
from coffer.infrastructure.memory.paths import (
    fact_path,
    memory_global_dir,
    memory_root,
    memory_store_dir,
)
from coffer.infrastructure.memory.scope_fs import git_root, project_ulid

__all__ = [
    "delete_fact_file",
    "fact_path",
    "git_root",
    "memory_global_dir",
    "memory_root",
    "memory_store_dir",
    "project_ulid",
    "read_fact_file",
    "regenerate_memory_index",
    "render_fact_markdown",
    "scan_store_dir",
    "write_fact_file",
]

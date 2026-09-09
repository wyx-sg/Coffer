"""On-disk adapters for a knowledge scope.

The index/retrieval engine lives in the shared substrate
``coffer.infrastructure.knowledge``; this package keeps the scope-specific
on-disk concerns — the per-entry / topic / rules / handoff file I/O, the
``knowledge/`` lane delta scan, git-root → project-ULID resolution, and the two
machine-local side tables (``knowledge_scope_project_roots`` /
``knowledge_scope_labels``).
"""

from __future__ import annotations

from coffer.infrastructure.knowledge_scope.files import (
    delete_fact_file,
    legacy_root_facts,
    read_fact_file,
    render_fact_markdown,
    scan_scope_dir,
    write_fact_file,
)
from coffer.infrastructure.knowledge_scope.paths import (
    fact_path,
    knowledge_root,
    scope_dir,
)
from coffer.infrastructure.knowledge_scope.scope_fs import git_root, project_ulid

__all__ = [
    "delete_fact_file",
    "fact_path",
    "git_root",
    "knowledge_root",
    "legacy_root_facts",
    "project_ulid",
    "read_fact_file",
    "render_fact_markdown",
    "scan_scope_dir",
    "scope_dir",
    "write_fact_file",
]

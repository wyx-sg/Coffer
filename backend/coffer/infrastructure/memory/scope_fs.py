"""Memory-face re-export of the shared scope helpers.

The implementation moved into the kind-agnostic substrate
(``infrastructure/knowledge/scope_fs``) so the KB face can share it for
per-project document scope (ADR-030) without a cross-kind import. Existing
memory call sites keep importing from here unchanged.
"""

from __future__ import annotations

from coffer.infrastructure.knowledge.scope_fs import git_root, project_ulid

__all__ = ["git_root", "project_ulid"]

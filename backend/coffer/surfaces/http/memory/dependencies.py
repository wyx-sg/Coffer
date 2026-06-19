"""Dependency providers for the memory-store side-repos.

Extracted from the kind-agnostic ``surfaces/http/dependencies`` so that core
stays under its file-size budget (mirrors how chat / distill DI live in their
own surface modules). These hold the two tiny ``store_name``-keyed repos that
the memory routes read and ``wiring`` populates at startup:

- ``ProjectRootRepo`` — the originating git-root (FR-017a readable identity).
- ``StoreLabelRepo`` — a user-set display label (FR-017c).
"""

from __future__ import annotations

from typing import Any

_project_root_repo: Any | None = None
_store_label_repo: Any | None = None


def set_project_root_repo(repo: Any) -> None:
    global _project_root_repo
    _project_root_repo = repo


def get_project_root_repo() -> Any:
    if _project_root_repo is None:
        raise RuntimeError("project-root repo not initialised")
    return _project_root_repo


def set_store_label_repo(repo: Any) -> None:
    global _store_label_repo
    _store_label_repo = repo


def get_store_label_repo() -> Any:
    if _store_label_repo is None:
        raise RuntimeError("store-label repo not initialised")
    return _store_label_repo

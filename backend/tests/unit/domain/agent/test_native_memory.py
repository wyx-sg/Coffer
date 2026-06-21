"""Unit tests for the native per-project memory domain helpers (spec 004).

Pure value-level logic: the per-type layout table and the lossy slug decoder.
"""

from __future__ import annotations

from coffer.domain.agent.native_memory import (
    NativeMemoryLayout,
    decode_project_slug,
    native_memory_layout_for,
)
from coffer.domain.agent.types import AgentType


def test_layout_for_claude_code_is_projects_memory() -> None:
    layout = native_memory_layout_for(AgentType.CLAUDE_CODE)
    assert layout == NativeMemoryLayout(projects_subdir="projects", memory_subdir="memory")


def test_layout_for_codex_is_none() -> None:
    assert native_memory_layout_for(AgentType.CODEX) is None


def test_decode_absolute_slug() -> None:
    # Leading '-' marks an absolute path; segments rejoin with '/'.
    assert decode_project_slug("-Users-xing-Coffer") == ("Coffer", "/Users/xing/Coffer")


def test_decode_relative_slug_without_leading_dash() -> None:
    # No leading dash -> relative-ish path; label is the last segment.
    assert decode_project_slug("home-user-repo") == ("repo", "home/user/repo")


def test_decode_empty_slug() -> None:
    assert decode_project_slug("") == ("", None)


def test_decode_slug_with_only_dashes() -> None:
    # All separators, no real segments -> treated as undecodable.
    assert decode_project_slug("---") == ("---", None)

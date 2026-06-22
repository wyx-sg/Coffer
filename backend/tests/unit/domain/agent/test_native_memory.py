"""Unit tests for the native per-project memory domain helpers (spec 004).

Pure value-level logic: the per-type layout table and the lossy slug decoder.
"""

from __future__ import annotations

from coffer.domain.agent.native_memory import (
    CodexGlobalLayout,
    NativeMemoryLayout,
    decode_project_slug,
    native_memory_layout_for,
    resolve_project_slug,
)
from coffer.domain.agent.types import AgentType


def test_layout_for_claude_code_is_projects_memory() -> None:
    layout = native_memory_layout_for(AgentType.CLAUDE_CODE)
    assert layout == NativeMemoryLayout(projects_subdir="projects", memory_subdir="memory")


def test_layout_for_codex_is_global_task_grouped() -> None:
    layout = native_memory_layout_for(AgentType.CODEX)
    assert layout == CodexGlobalLayout(memory_subdir="memories", index_file="MEMORY.md")


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


def test_resolve_disambiguates_hyphenated_leaf_via_filesystem() -> None:
    # The real project is /Users/xing/wedding-invitation (a hyphen in the leaf).
    # The lossy decoder would split it into .../wedding/invitation → label
    # "invitation"; the FS-aware resolver keeps it whole.
    existing = {"/Users", "/Users/xing", "/Users/xing/wedding-invitation"}
    label, path = resolve_project_slug("-Users-xing-wedding-invitation", lambda p: p in existing)
    assert (label, path) == ("wedding-invitation", "/Users/xing/wedding-invitation")


def test_resolve_prefers_longest_existing_dir_name() -> None:
    # A multi-hyphen single directory (a-b-c) is taken whole when it exists.
    existing = {"/Users", "/Users/xing", "/Users/xing/a-b-c"}
    assert resolve_project_slug("-Users-xing-a-b-c", lambda p: p in existing) == (
        "a-b-c",
        "/Users/xing/a-b-c",
    )


def test_resolve_falls_back_to_lossy_when_nothing_on_disk() -> None:
    # Project dir gone → no prefix exists → same result as the lossy decoder.
    assert resolve_project_slug("-Users-xing-Coffer", lambda _p: False) == (
        "Coffer",
        "/Users/xing/Coffer",
    )

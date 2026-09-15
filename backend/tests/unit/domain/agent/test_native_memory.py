"""Unit tests for the native per-project memory domain helpers (spec agent-registry).

Pure value-level logic: the per-type layout table, the lossy slug decoder, and
the filesystem-aware slug resolver. ``resolve_project_slug`` takes an injected
``list_dirs`` callable rather than touching a real directory, so its tests
build a small fake tree (a ``dict[str, list[str]]`` of absolute path ->
child directory names) instead of a real one — the same algorithm gets
exercised against a *real* filesystem in
``tests/unit/memory/test_claude_code_reader.py``, via the real adapter
``infrastructure.memory.readers.claude_code`` composes it with.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable

from coffer.domain.agent.native_memory import (
    CodexGlobalLayout,
    NativeMemoryLayout,
    decode_project_slug,
    is_native_memory_dir,
    native_memory_layout_for,
    resolve_project_slug,
)
from coffer.domain.agent.types import AgentType


def _fake_tree(tree: dict[str, list[str]]) -> Callable[[str], list[str]]:
    return lambda path: tree.get(path, [])


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
    # The lossy decoder would split it into .../wedding/invitation -> label
    # "invitation"; the FS-aware resolver keeps it whole.
    tree = {
        "/": ["Users"],
        "/Users": ["xing"],
        "/Users/xing": ["wedding-invitation"],
    }
    label, path = resolve_project_slug("-Users-xing-wedding-invitation", _fake_tree(tree))
    assert (label, path) == ("wedding-invitation", "/Users/xing/wedding-invitation")


def test_resolve_prefers_longest_existing_dir_name() -> None:
    # A multi-hyphen single directory (a-b-c) is taken whole when it exists.
    tree = {
        "/": ["Users"],
        "/Users": ["xing"],
        "/Users/xing": ["a-b-c"],
    }
    assert resolve_project_slug("-Users-xing-a-b-c", _fake_tree(tree)) == (
        "a-b-c",
        "/Users/xing/a-b-c",
    )


def test_resolve_falls_back_to_lossy_when_nothing_on_disk() -> None:
    # Project dir gone -> no prefix exists -> same result as the lossy decoder.
    assert resolve_project_slug("-Users-xing-Coffer", _fake_tree({})) == (
        "Coffer",
        "/Users/xing/Coffer",
    )


def test_resolve_recovers_a_dot_in_the_real_name_from_the_filesystem() -> None:
    # Mirrors a real slug on this machine: `-Users-yuxing-wu` decodes to
    # `/Users/yuxing.wu` -- the dot was encoded the same way `/` was, so only
    # checking the real directory listing (not the slug string) recovers it.
    tree = {
        "/": ["Users"],
        "/Users": ["yuxing.wu"],
        "/Users/yuxing.wu": ["proj"],
    }
    assert resolve_project_slug("-Users-yuxing-wu-proj", _fake_tree(tree)) == (
        "proj",
        "/Users/yuxing.wu/proj",
    )


def test_resolve_backtracks_past_a_longer_dead_end_match() -> None:
    # `ab-cd` (a real, but unrelated, sibling directory) is a longer prefix
    # match of the slug than `ab` is, but has no `ef` child -- only `ab` leads
    # anywhere, and only backtracking past the greedy longest match finds it.
    tree = {
        "/": ["ab-cd", "ab"],
        "/ab-cd": [],
        "/ab": ["cd-ef"],
    }
    assert resolve_project_slug("-ab-cd-ef", _fake_tree(tree)) == ("cd-ef", "/ab/cd-ef")


def test_resolve_the_home_directory_itself_can_be_the_project() -> None:
    tree = {
        "/": ["Users"],
        "/Users": ["tester"],
    }
    assert resolve_project_slug("-Users-tester", _fake_tree(tree)) == (
        "tester",
        "/Users/tester",
    )


def test_resolve_without_leading_dash_delegates_to_the_lossy_decoder() -> None:
    assert resolve_project_slug("home-user-repo", _fake_tree({"/": ["home"]})) == (
        "repo",
        "home/user/repo",
    )


# ---------------------------------------------------------------------------
# is_native_memory_dir — which directories a store's page may open
# ---------------------------------------------------------------------------


def test_is_native_memory_dir_accepts_only_the_layouts_own_shape() -> None:
    """A client names the directory, so "is this a store" must be a real question.

    Anything looser — "somewhere under the config dir" — would turn a surface
    that says "memory" into a reader for the agent's transcripts, settings and
    plugin cache, all of which live in the same tree.
    """
    config = pathlib.Path("/home/u/.claude")
    layout = native_memory_layout_for(AgentType.CLAUDE_CODE)
    store = config / "projects" / "-p-alpha" / "memory"

    assert is_native_memory_dir(layout, config, store) is True
    # The project dir holds the store, but is not one.
    assert is_native_memory_dir(layout, config, store.parent) is False
    # A sibling of the store under the same project is not one either.
    assert is_native_memory_dir(layout, config, store.with_name("todos")) is False
    # Nor is a "memory" dir at the wrong depth.
    assert is_native_memory_dir(layout, config, config / "memory") is False


def test_is_native_memory_dir_for_codex_is_the_single_global_store() -> None:
    config = pathlib.Path("/home/u/.codex")
    layout = native_memory_layout_for(AgentType.CODEX)
    assert is_native_memory_dir(layout, config, config / "memories") is True
    assert is_native_memory_dir(layout, config, config / "sessions") is False


def test_an_agent_type_with_no_layout_contains_no_store() -> None:
    """No layout is not "everything is a store"; it is "there are none"."""
    assert is_native_memory_dir(None, pathlib.Path("/home/u"), pathlib.Path("/home/u/x")) is False

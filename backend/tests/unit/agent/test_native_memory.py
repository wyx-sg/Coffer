"""Unit: scanning an agent's native (on-disk) memory."""

from __future__ import annotations

import os

from coffer.application.agent.native_memory import scan_claude_native_memory


def _make_project(config_dir, slug: str, facts: list[str]) -> None:
    mem = config_dir / "projects" / slug / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("# index\n", encoding="utf-8")
    for name in facts:
        (mem / f"{name}.md").write_text(f"a fact about {name}\n", encoding="utf-8")


def test_scan_lists_projects_with_fact_counts(tmp_path):
    _make_project(tmp_path, "-Users-x-WorkEnv-AI-Coffer", ["build", "deploy", "naming"])
    _make_project(tmp_path, "-Users-x-WorkEnv-AI-Other", ["one"])
    # A project dir with no memory dir is ignored.
    (tmp_path / "projects" / "-Users-x-empty").mkdir(parents=True)

    found = scan_claude_native_memory(tmp_path)
    by_slug = {p.slug: p for p in found}
    assert set(by_slug) == {"-Users-x-WorkEnv-AI-Coffer", "-Users-x-WorkEnv-AI-Other"}
    # MEMORY.md is the index, not a fact.
    assert by_slug["-Users-x-WorkEnv-AI-Coffer"].fact_count == 3
    assert by_slug["-Users-x-WorkEnv-AI-Other"].fact_count == 1
    assert all(p.managed is False for p in found)


def test_scan_marks_a_symlinked_memory_dir_as_managed(tmp_path):
    # Coffer-managed store the symlink points at.
    store = tmp_path / "coffer-store"
    store.mkdir()
    (store / "fact.md").write_text("x\n", encoding="utf-8")
    proj = tmp_path / "projects" / "-Users-x-Managed"
    proj.mkdir(parents=True)
    os.symlink(store, proj / "memory")

    (found,) = scan_claude_native_memory(tmp_path)
    assert found.slug == "-Users-x-Managed"
    assert found.managed is True


def test_scan_missing_projects_dir_returns_empty(tmp_path):
    assert scan_claude_native_memory(tmp_path) == []


def test_decode_claude_slug_round_trips_via_filesystem(tmp_path):
    from coffer.application.agent.native_memory import decode_claude_slug, _full_slug

    # Build a real path with a dotted + underscored component.
    proj = tmp_path / "my.proj" / "sub_dir"
    proj.mkdir(parents=True)
    slug = _full_slug(proj)
    assert "-" in slug
    assert decode_claude_slug(slug) == proj


def test_decode_claude_slug_returns_none_for_nonexistent(tmp_path):
    from coffer.application.agent.native_memory import decode_claude_slug

    assert decode_claude_slug("-no-such-path-anywhere-xyz") is None

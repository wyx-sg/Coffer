"""Unit tests for the Codex global-memory infra reader (spec 004 FR-040).

``codex_stores`` turns ``memories/MEMORY.md`` into one ``ScannedStore`` per
distinct routed cwd; ``read_codex_facts`` returns the Task-Group blocks routed to
a given project path, ready to import as memories.
"""

from __future__ import annotations

import pathlib

from coffer.infrastructure.agent.codex_memory_store import codex_stores, read_codex_facts

_DOC = """\
# Task Group: gateway debugging

scope: x
applies_to: cwd=/projects/account-gateway; reuse_rule=x

## Task 1: a, success

# Task Group: gateway more

scope: y
applies_to: cwd=/projects/account-gateway; reuse_rule=y

## Task 1: b, success

# Task Group: bff work

scope: z
applies_to: cwd=/projects/account-bff and /projects/account; reuse_rule=z

## Task 1: c, success
"""


def _write_doc(memories: pathlib.Path, text: str = _DOC) -> None:
    memories.mkdir(parents=True, exist_ok=True)
    (memories / "MEMORY.md").write_text(text, encoding="utf-8")


def test_codex_stores_groups_by_cwd_with_counts(tmp_path: pathlib.Path) -> None:
    memories = tmp_path / "memories"
    _write_doc(memories)

    stores = {s.project_path: s for s in codex_stores(memories, "MEMORY.md")}

    # account-gateway appears in two groups; the multi-path group adds bff + account.
    assert stores["/projects/account-gateway"].item_count == 2
    assert stores["/projects/account-bff"].item_count == 1
    assert stores["/projects/account"].item_count == 1
    # All rows share the one global memory dir.
    assert all(s.memory_dir == str(memories) for s in stores.values())


def test_codex_stores_empty_when_no_index(tmp_path: pathlib.Path) -> None:
    (tmp_path / "memories").mkdir()
    assert codex_stores(tmp_path / "memories", "MEMORY.md") == []
    assert codex_stores(tmp_path / "nope", "MEMORY.md") == []


def test_read_codex_facts_returns_blocks_routed_to_path(tmp_path: pathlib.Path) -> None:
    memories = tmp_path / "memories"
    _write_doc(memories)

    facts = read_codex_facts(memories, "/projects/account-gateway", "MEMORY.md")
    assert len(facts) == 2
    titles = {f.name for f in facts}
    assert titles == {"gateway debugging", "gateway more"}
    assert all(f.description == "" and f.origin_session_id is None for f in facts)
    assert "## Task 1: a" in facts[0].body or "## Task 1: a" in facts[1].body


def test_read_codex_facts_multi_path_group_routes_to_each(tmp_path: pathlib.Path) -> None:
    memories = tmp_path / "memories"
    _write_doc(memories)

    assert {f.name for f in read_codex_facts(memories, "/projects/account-bff", "MEMORY.md")} == {
        "bff work"
    }
    assert {f.name for f in read_codex_facts(memories, "/projects/account", "MEMORY.md")} == {
        "bff work"
    }


def test_read_codex_facts_unknown_path_yields_nothing(tmp_path: pathlib.Path) -> None:
    memories = tmp_path / "memories"
    _write_doc(memories)
    assert read_codex_facts(memories, "/projects/nonexistent", "MEMORY.md") == []

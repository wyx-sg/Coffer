"""Unit tests for the Codex global-memory infra reader.

``codex_stores`` turns ``memories/MEMORY.md`` into one ``ScannedStore`` per
distinct routed cwd — the read-only listing behind the agent detail page's
Memory tab.
"""

from __future__ import annotations

import pathlib

from coffer.infrastructure.agent.codex_memory_store import codex_stores

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
    # The slug keeps the raw cwd as written in the document.
    assert stores["/projects/account-gateway"].slug == "/projects/account-gateway"


def test_codex_stores_expands_home_relative_cwd(tmp_path: pathlib.Path) -> None:
    memories = tmp_path / "memories"
    _write_doc(
        memories,
        "# Task Group: home\n\napplies_to: cwd=~/work/thing; reuse_rule=x\n\n"
        "## Task 1: a, success\n",
    )

    store = codex_stores(memories, "MEMORY.md")[0]
    # The slug is verbatim; the project path is expanded for display/actions.
    assert store.slug == "~/work/thing"
    assert store.project_path == str(pathlib.Path.home() / "work/thing")


def test_codex_stores_empty_when_no_index(tmp_path: pathlib.Path) -> None:
    (tmp_path / "memories").mkdir()
    assert codex_stores(tmp_path / "memories", "MEMORY.md") == []
    assert codex_stores(tmp_path / "nope", "MEMORY.md") == []


def test_codex_stores_empty_when_document_has_no_task_groups(tmp_path: pathlib.Path) -> None:
    memories = tmp_path / "memories"
    _write_doc(memories, "# User Profile\n\njust prose, no task groups\n")
    assert codex_stores(memories, "MEMORY.md") == []

"""Fact files are read and written by filesystem calls only (unit tier, real
``tmp_path``, no database) — the round-trip requirement is the whole point of
this module, so these tests build every kind of ``Fact`` the domain allows and
check it comes back identical.

``COFFER_MEMORY_ROOT`` is pinned to ``tmp_path`` by the suite-wide
``_isolated_memory_root`` fixture (``backend/tests/conftest.py``); nothing
here can reach a developer's real memory tree.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.memory.fact import (
    STATUS_ACTIVE,
    STATUS_SUPERSEDED,
    TYPE_FEEDBACK,
    TYPE_PROJECT,
    Fact,
    Origin,
)
from coffer.infrastructure.memory import paths, store


def _fact(**overrides: object) -> Fact:
    defaults: dict[str, object] = {
        "slug": "worktree-development",
        "title": "Develop in a worktree",
        "description": "Always develop in a git worktree for this repo",
        "type": TYPE_FEEDBACK,
        "body": "Always develop in a git worktree — multiple parallel sessions share the repo.",
        "partition": "coffer",
        "origins": (
            Origin(
                agent="claude_code",
                native_path="/home/dev/.claude/projects/coffer/memory/feedback-worktree.md",
                anchor="",
                captured_at="2026-09-12T00:00:00+00:00",
                source_written_at="2026-09-01T00:00:00+00:00",
            ),
        ),
    }
    defaults.update(overrides)
    return Fact(**defaults)  # type: ignore[arg-type]


def test_write_fact_returns_the_relative_path() -> None:
    fact = _fact()
    relpath = store.write_fact(fact)
    assert relpath == str(pathlib.Path("coffer") / "facts" / "worktree-development.md")


def test_round_trip_is_exact_for_a_plain_fact() -> None:
    fact = _fact()
    store.write_fact(fact)
    assert store.read_fact(fact.partition, fact.slug) == fact


def test_round_trip_is_exact_with_two_origins() -> None:
    fact = _fact(
        origins=(
            Origin(agent="claude_code", native_path="/a/memory/x.md", anchor=""),
            Origin(agent="codex", native_path="/b/MEMORY.md", anchor="group-3"),
        )
    )
    store.write_fact(fact)
    assert store.read_fact(fact.partition, fact.slug) == fact


def test_round_trip_is_exact_when_superseded() -> None:
    fact = _fact(
        status=STATUS_SUPERSEDED,
        superseded_by="abc123def456",
        conflicts_with=("111111111111",),
    )
    store.write_fact(fact)
    assert store.read_fact(fact.partition, fact.slug) == fact


@pytest.mark.parametrize(
    "body",
    [
        "",
        "no trailing newline",
        "trailing newline\n",
        "blank line at the end\n\n",
        "multiple\nlines\nin\nthe\nbody",
        "  leading and trailing whitespace  ",
    ],
)
def test_round_trip_preserves_the_body_byte_for_byte(body: str) -> None:
    fact = _fact(body=body)
    store.write_fact(fact)
    assert store.read_fact(fact.partition, fact.slug).body == body


def test_round_trip_is_exact_in_the_global_partition() -> None:
    fact = _fact(
        partition="global",
        type=TYPE_FEEDBACK,
        slug="reply-in-chinese",
    )
    store.write_fact(fact)
    assert store.read_fact("global", "reply-in-chinese") == fact


def test_write_fact_is_atomic_and_leaves_no_tmp_file() -> None:
    fact = _fact()
    store.write_fact(fact)
    directory = paths.facts_dir(fact.partition)
    names = {p.name for p in directory.iterdir()}
    assert names == {"worktree-development.md"}


def test_read_fact_raises_when_absent() -> None:
    with pytest.raises(store.FactNotFound):
        store.read_fact("coffer", "does-not-exist")


def test_list_facts_is_empty_for_an_unknown_partition() -> None:
    assert store.list_facts("nothing-here") == ()


def test_list_facts_returns_every_fact_sorted_by_slug() -> None:
    store.write_fact(_fact(slug="zzz-last"))
    store.write_fact(_fact(slug="aaa-first"))
    facts = store.list_facts("coffer")
    assert [f.slug for f in facts] == ["aaa-first", "zzz-last"]


def test_list_partitions_is_empty_before_anything_is_written() -> None:
    assert store.list_partitions() == ()


def test_list_partitions_lists_every_partition_directory() -> None:
    store.write_fact(_fact(partition="coffer"))
    store.write_fact(_fact(partition="global", slug="a-preference"))
    assert store.list_partitions() == ("coffer", "global")


def test_delete_partition_removes_everything_under_it() -> None:
    store.write_fact(_fact())
    store.write_readme("coffer", "/home/dev/coffer")
    store.delete_partition("coffer")
    assert not paths.partition_dir("coffer").exists()
    assert store.list_partitions() == ()


def test_delete_partition_is_a_no_op_when_absent() -> None:
    store.delete_partition("never-existed")  # does not raise


def test_clear_facts_removes_facts_but_keeps_the_readme() -> None:
    store.write_fact(_fact())
    store.write_readme("coffer", "/home/dev/coffer")
    store.clear_facts("coffer")
    assert store.list_facts("coffer") == ()
    assert paths.readme_path("coffer").is_file()


def test_clear_facts_is_a_no_op_when_the_partition_does_not_exist() -> None:
    store.clear_facts("never-existed")  # does not raise


def test_write_readme_names_the_project_root_for_a_project_partition() -> None:
    store.write_readme("coffer", "/home/dev/coffer")
    content = paths.readme_path("coffer").read_text(encoding="utf-8")
    assert "/home/dev/coffer" in content


def test_write_readme_describes_the_global_partition_without_a_project_root() -> None:
    store.write_readme("global", "/home/dev/coffer")
    content = paths.readme_path("global").read_text(encoding="utf-8")
    assert "person" in content
    assert "/home/dev/coffer" not in content


def test_a_hand_edited_file_with_malformed_yaml_degrades_to_empty_frontmatter() -> None:
    path = paths.fact_path("coffer", "broken")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\ntitle: [unterminated\n---\nthe body survives\n", encoding="utf-8")
    fact = store.read_fact("coffer", "broken")
    assert fact.title == ""
    assert fact.body == "the body survives\n"
    assert fact.status == STATUS_ACTIVE


def test_a_file_with_no_frontmatter_reads_as_a_bare_body() -> None:
    path = paths.fact_path("coffer", "no-frontmatter")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("just some text, no fence at all", encoding="utf-8")
    fact = store.read_fact("coffer", "no-frontmatter")
    assert fact.title == ""
    assert fact.body == "just some text, no fence at all"


def test_write_fact_overwrites_an_existing_file_in_place() -> None:
    store.write_fact(_fact(title="first version"))
    store.write_fact(_fact(title="second version"))
    assert store.read_fact("coffer", "worktree-development").title == "second version"


def test_type_project_round_trips() -> None:
    fact = _fact(type=TYPE_PROJECT, partition="coffer")
    store.write_fact(fact)
    assert store.read_fact(fact.partition, fact.slug).type == TYPE_PROJECT

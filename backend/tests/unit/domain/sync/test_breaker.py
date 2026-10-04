"""The deletion breaker's arithmetic (spec vault-sync "Hold a round that would
lose too much", "Count losses, not deletions", "Ask git about renames
separately from the applied diff", "Never apply the registry or the manifest")."""

from __future__ import annotations

import pytest

from coffer.domain.sync.breaker import FLOOR, SHARE, PathDelta, breached, losses, totals
from coffer.domain.vault.content_ids import EMPTY_BLOB


def _gone(paths: list[str]) -> list[PathDelta]:
    return [PathDelta(p, "D", f"blob-{p}") for p in paths]


@pytest.mark.acceptance(
    spec="vault-sync", scenario="the guard trips above a fifth of an area or at twenty documents"
)
def test_the_thresholds_are_a_fifth_of_an_area_or_twenty_files() -> None:
    assert (SHARE, FLOOR) == (0.2, 20)
    area = [f"knowledge/team/n{i}.md" for i in range(10)]
    before = totals(area)
    assert breached(losses(_gone(area[:2])), before) == []  # exactly 20%
    (over,) = breached(losses(_gone(area[:3])), before)
    assert (over.area, over.lost, over.total) == ("knowledge", 3, 10)
    large = [f"knowledge/big/n{i}.md" for i in range(500)]
    (floor,) = breached(losses(_gone(large[:20])), totals(large))
    assert floor.lost == 20
    assert breached(losses(_gone(large[:19])), totals(large)) == []


@pytest.mark.acceptance(spec="vault-sync", scenario="a re-layout publishes without asking")
def test_content_that_lands_elsewhere_in_its_area_is_a_move() -> None:
    moved = [PathDelta(f"knowledge/team/n{i}.md", "D", f"b{i}") for i in range(30)]
    moved += [PathDelta(f"knowledge/team/archive/n{i}.md", "A", f"b{i}") for i in range(30)]
    moved.append(PathDelta("knowledge/team/gone.md", "D", "lost"))
    assert losses(moved) == ["knowledge/team/gone.md"]
    # The same bytes in another area were not moved: they are asked about.
    across = [PathDelta("knowledge/a.md", "D", "b"), PathDelta("skills/a.md", "A", "b")]
    assert losses(across) == ["knowledge/a.md"]
    # Every empty file is the same file: an empty one never pairs.
    empty = [
        PathDelta("knowledge/e.md", "D", EMPTY_BLOB),
        PathDelta("knowledge/f.md", "A", EMPTY_BLOB),
    ]
    assert losses(empty) == ["knowledge/e.md"]


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a re-layout that rewrites its documents publishes without asking"
)
def test_a_pairing_git_found_is_a_move_only_inside_one_area() -> None:
    edited = [
        PathDelta("knowledge/old/n.md", "D", "b1"),
        PathDelta("knowledge/new/n.md", "A", "b2"),
    ]
    assert losses(edited, renames=[("knowledge/old/n.md", "knowledge/new/n.md")]) == []
    assert losses(edited, renames=[("knowledge/old/n.md", "skills/n.md")]) == ["knowledge/old/n.md"]


def test_a_resource_file_is_lost_only_when_its_uid_is_gone() -> None:
    deltas = [
        PathDelta("resources/skill/a.json", "D", "x"),
        PathDelta("resources/skill/b.json", "D", "y"),
    ]
    uids = {"resources/skill/a.json": "u-a", "resources/skill/b.json": "u-b"}
    assert losses(deltas, uids_before=uids, uids_after=["u-a"]) == ["resources/skill/b.json"]


@pytest.mark.acceptance(spec="vault-sync", scenario="the registry and manifest are never applied")
def test_descriptors_and_the_manifest_are_never_counted() -> None:
    gone = _gone([f"machines/m{i}.json" for i in range(30)] + ["manifest.json"])
    assert losses(gone) == []

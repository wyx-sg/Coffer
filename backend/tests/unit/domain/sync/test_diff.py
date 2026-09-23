"""What a converge round changes, and the deletion guard over it.

Covers `openspec/specs/vault-sync/spec.md` "Applying a diff" and "Safety" (the
oversized-deletion hold), for the pure domain in `coffer.domain.sync.diff`.
"""

from __future__ import annotations

import pytest

from coffer.domain.sync.diff import (
    DEFAULT_DELETION_FLOOR,
    DEFAULT_DELETION_SHARE,
    EMPTY_BLOB,
    ChangeStatus,
    DeletionGuard,
    DiffSummary,
    DocChange,
    area_of,
)


def _deletions(area: str, count: int) -> list[DocChange]:
    return [DocChange(f"{area}/doc-{i}.md", ChangeStatus.DELETED) for i in range(count)]


# --- area_of / DocChange ----------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("knowledge/global/a.md", "knowledge"),
        ("skills/coffer-vault/SKILL.md", "skills"),
        ("resources/logo.png", "resources"),
        ("state/pointer.json", "state"),
        ("credentials/github.enc", "credentials"),
        ("machines/abc123.yaml", "machines"),
    ],
)
def test_every_bundle_prefix_maps_to_its_own_area(path: str, expected: str) -> None:
    assert area_of(path) == expected


@pytest.mark.parametrize("path", ["manifest.json", "README.md", "", "knowledge", "knowledgeable/a"])
def test_paths_outside_the_known_prefixes_fall_through_to_manifest(path: str) -> None:
    # The prefixes carry their trailing slash, so a bare directory name or a
    # longer word starting with one is not that area.
    assert area_of(path) == "manifest"


def test_doc_change_reports_its_area_from_its_path() -> None:
    assert DocChange("knowledge/a.md", ChangeStatus.ADDED).area == "knowledge"


@pytest.mark.parametrize(
    ("path", "touches"),
    [
        ("knowledge/a.md", True),
        ("credentials/x.enc", True),
        ("state/pointer.json", True),
        ("machines/abc.yaml", False),
        ("manifest.json", False),
    ],
)
def test_registry_and_manifest_are_the_only_areas_that_miss_the_vault(
    path: str, touches: bool
) -> None:
    assert DocChange(path, ChangeStatus.MODIFIED).touches_vault is touches


# --- DiffSummary ------------------------------------------------------------


def test_summary_orders_changes_by_path() -> None:
    summary = DiffSummary.of(
        [
            DocChange("skills/z.md", ChangeStatus.ADDED),
            DocChange("knowledge/a.md", ChangeStatus.DELETED),
            DocChange("knowledge/b.md", ChangeStatus.MODIFIED),
        ]
    )
    assert [c.path for c in summary.changes] == [
        "knowledge/a.md",
        "knowledge/b.md",
        "skills/z.md",
    ]


def test_a_summary_is_falsy_only_when_nothing_changed() -> None:
    assert not DiffSummary.of([])
    assert not DiffSummary()
    assert DiffSummary.of([DocChange("manifest.json", ChangeStatus.MODIFIED)])


@pytest.mark.acceptance(spec="vault-sync", scenario="the registry and manifest are never applied")
def test_vault_changes_drops_registry_and_manifest_entries() -> None:
    summary = DiffSummary.of(
        [
            DocChange("knowledge/a.md", ChangeStatus.ADDED),
            DocChange("machines/abc.yaml", ChangeStatus.MODIFIED),
            DocChange("manifest.json", ChangeStatus.MODIFIED),
        ]
    )
    assert [c.path for c in summary.vault_changes] == ["knowledge/a.md"]


def test_counts_report_all_three_statuses_even_when_a_status_is_unused() -> None:
    summary = DiffSummary.of(
        [
            DocChange("knowledge/a.md", ChangeStatus.ADDED),
            DocChange("knowledge/b.md", ChangeStatus.ADDED),
            DocChange("skills/c.md", ChangeStatus.MODIFIED),
        ]
    )
    assert summary.counts() == {"added": 2, "modified": 1, "deleted": 0}


def test_counts_ignore_changes_that_never_reach_the_vault() -> None:
    summary = DiffSummary.of(
        [
            DocChange("manifest.json", ChangeStatus.MODIFIED),
            DocChange("machines/abc.yaml", ChangeStatus.ADDED),
            DocChange("machines/def.yaml", ChangeStatus.DELETED),
        ]
    )
    assert summary.counts() == {"added": 0, "modified": 0, "deleted": 0}


def test_paths_returns_only_vault_paths_of_the_requested_status() -> None:
    summary = DiffSummary.of(
        [
            DocChange("knowledge/gone.md", ChangeStatus.DELETED),
            DocChange("skills/also-gone.md", ChangeStatus.DELETED),
            DocChange("machines/abc.yaml", ChangeStatus.DELETED),
            DocChange("knowledge/kept.md", ChangeStatus.MODIFIED),
        ]
    )
    assert summary.paths(ChangeStatus.DELETED) == ("knowledge/gone.md", "skills/also-gone.md")
    assert summary.paths(ChangeStatus.MODIFIED) == ("knowledge/kept.md",)
    assert summary.paths(ChangeStatus.ADDED) == ()


# --- DeletionGuard validation ----------------------------------------------


def test_guard_defaults_match_the_published_constants() -> None:
    guard = DeletionGuard()
    assert (guard.share, guard.floor) == (DEFAULT_DELETION_SHARE, DEFAULT_DELETION_FLOOR)


@pytest.mark.parametrize("share", [0.0, -0.1, 1.01, 2.0])
def test_a_share_outside_zero_to_one_is_rejected(share: float) -> None:
    with pytest.raises(ValueError, match="deletion share"):
        DeletionGuard(share=share)


def test_a_share_of_one_is_accepted_as_the_upper_bound() -> None:
    assert DeletionGuard(share=1.0).share == 1.0


@pytest.mark.parametrize("floor", [0, -1])
def test_a_floor_below_one_is_rejected(floor: int) -> None:
    with pytest.raises(ValueError, match="deletion floor"):
        DeletionGuard(floor=floor)


# --- DeletionGuard.breached_areas ------------------------------------------


def test_deletions_under_both_thresholds_do_not_breach() -> None:
    guard = DeletionGuard(share=0.2, floor=20)
    breached = guard.breached_areas(_deletions("knowledge", 2), {"knowledge": 10})
    assert breached == []


def test_a_share_exactly_at_the_threshold_does_not_breach() -> None:
    # The guard trips on *exceeding* the share, so 2 of 10 at share 0.2 is
    # still an ordinary round.
    guard = DeletionGuard(share=0.2, floor=20)
    assert guard.breached_areas(_deletions("knowledge", 2), {"knowledge": 10}) == []


def test_a_share_above_the_threshold_breaches() -> None:
    guard = DeletionGuard(share=0.2, floor=20)
    assert guard.breached_areas(_deletions("knowledge", 3), {"knowledge": 10}) == [
        ("knowledge", 3, 10)
    ]


def test_the_absolute_floor_catches_a_large_area_losing_a_lot() -> None:
    # 5 of 1000 is 0.5% — far under any share, but the floor is what stops a
    # big vault bleeding out a chunk at a time.
    guard = DeletionGuard(share=0.5, floor=5)
    assert guard.breached_areas(_deletions("knowledge", 5), {"knowledge": 1000}) == [
        ("knowledge", 5, 1000)
    ]
    assert guard.breached_areas(_deletions("knowledge", 4), {"knowledge": 1000}) == []


def test_deleting_from_an_area_this_side_believes_is_empty_always_breaches() -> None:
    guard = DeletionGuard(share=1.0, floor=1000)
    assert guard.breached_areas(_deletions("skills", 1), {"skills": 0}) == [("skills", 1, 0)]


def test_an_area_absent_from_totals_is_treated_as_empty() -> None:
    guard = DeletionGuard(share=1.0, floor=1000)
    assert guard.breached_areas(_deletions("skills", 1), {}) == [("skills", 1, 0)]


def test_only_deletions_count_towards_the_guard() -> None:
    guard = DeletionGuard(share=0.2, floor=2)
    changes = [
        DocChange("knowledge/a.md", ChangeStatus.ADDED),
        DocChange("knowledge/b.md", ChangeStatus.MODIFIED),
        DocChange("knowledge/c.md", ChangeStatus.ADDED),
    ]
    assert guard.breached_areas(changes, {"knowledge": 3}) == []


@pytest.mark.acceptance(spec="vault-sync", scenario="the registry and manifest are never applied")
def test_registry_and_manifest_deletions_never_trip_the_guard() -> None:
    guard = DeletionGuard(share=0.2, floor=1)
    changes = [
        DocChange("machines/abc.yaml", ChangeStatus.DELETED),
        DocChange("manifest.json", ChangeStatus.DELETED),
    ]
    assert guard.breached_areas(changes, {}) == []


def test_breached_areas_are_reported_once_each_in_area_order() -> None:
    guard = DeletionGuard(share=0.2, floor=20)
    changes = _deletions("skills", 4) + _deletions("knowledge", 5) + _deletions("state", 1)
    breached = guard.breached_areas(changes, {"skills": 5, "knowledge": 6, "state": 100})
    assert breached == [("knowledge", 5, 6), ("skills", 4, 5)]


def test_an_iterator_of_changes_is_consumed_once_and_still_scored() -> None:
    guard = DeletionGuard(share=0.2, floor=20)
    changes = iter(_deletions("knowledge", 9))
    assert guard.breached_areas(changes, {"knowledge": 10}) == [("knowledge", 9, 10)]


# --- moves are not losses (spec vault-sync FR-090) --------------------------


def _relayout(count: int, *, from_dir: str = "", to_dir: str = "sources/") -> list[DocChange]:
    """``count`` knowledge documents moved, as git reports a move: the delete
    and the add of identical content, paired by nothing but that content."""
    changes = []
    for i in range(count):
        blob = f"{i:040x}"
        changes.append(DocChange(f"knowledge/c/{from_dir}d{i}.md", ChangeStatus.DELETED, blob=blob))
        changes.append(DocChange(f"knowledge/c/{to_dir}d{i}.md", ChangeStatus.ADDED, blob=blob))
    return changes


def test_a_relayout_of_almost_every_document_does_not_breach() -> None:
    """The bug this exists for: the knowledge two-lane rewrite moved 56 of 58
    documents into a subdirectory, and the round sat held for a day."""
    guard = DeletionGuard()
    assert guard.breached_areas(_relayout(56), {"knowledge": 58}) == []


def test_the_same_scale_of_deletion_without_the_additions_still_breaches() -> None:
    """The other half of the pair, and the one that must not change: 56 of 58
    documents deleted with nothing receiving their content is a loss."""
    guard = DeletionGuard()
    lost = [c for c in _relayout(56) if c.status is ChangeStatus.DELETED]
    assert guard.breached_areas(lost, {"knowledge": 58}) == [("knowledge", 56, 58)]


def test_a_deletion_with_no_content_id_counts() -> None:
    """A path reconstructed from the retry set carries no content id, and a
    deletion that cannot be shown to be a move is counted as a loss."""
    guard = DeletionGuard()
    assert guard.breached_areas(_deletions("knowledge", 25), {"knowledge": 30}) == [
        ("knowledge", 25, 30)
    ]


def test_a_move_that_also_edits_the_document_counts_when_nothing_paired_it() -> None:
    """With no pairing to go on there is only content, and different bytes at
    another path are indistinguishable from a deletion standing beside an
    unrelated addition. So it is asked about."""
    guard = DeletionGuard(share=0.2, floor=20)
    changes = [
        DocChange("knowledge/c/d0.md", ChangeStatus.DELETED, blob="a" * 40),
        DocChange("knowledge/c/sources/d0.md", ChangeStatus.ADDED, blob="b" * 40),
    ]
    assert guard.breached_areas(changes, {"knowledge": 1}) == [("knowledge", 1, 1)]


def test_a_move_that_also_edits_the_document_is_a_move_once_git_pairs_it() -> None:
    """The 2026-09-19 shape: giving every resource an immutable uid renamed
    each document *and* added a ``uid:`` line to it, so exact-bytes pairing saw
    28 of 28 resources disappear and held the vault for four days. git had
    reported the same diff as 28 renames all along."""
    guard = DeletionGuard(share=0.2, floor=20)
    changes = [
        DocChange("resources/agent/codex.yaml", ChangeStatus.DELETED, blob="a" * 40),
        DocChange("resources/agent/bc0eff32.yaml", ChangeStatus.ADDED, blob="b" * 40),
    ]
    renames = [("resources/agent/codex.yaml", "resources/agent/bc0eff32.yaml")]
    assert guard.breached_areas(changes, {"resources": 1}, renames) == []


def test_a_pairing_that_crosses_an_area_is_not_a_move() -> None:
    """git pairs renames over the whole tree; the guard's unit is the area, so
    the domain filters rather than trusts. Same content, wrong place, still
    asked about."""
    guard = DeletionGuard(share=0.2, floor=20)
    changes = [
        DocChange("knowledge/c/d0.md", ChangeStatus.DELETED, blob="a" * 40),
        DocChange("credentials/c/d0.md", ChangeStatus.ADDED, blob="b" * 40),
    ]
    renames = [("knowledge/c/d0.md", "credentials/c/d0.md")]
    assert guard.breached_areas(changes, {"knowledge": 1}, renames) == [("knowledge", 1, 1)]


def test_a_wiped_area_is_held_even_though_pairings_are_now_consulted() -> None:
    """The argument for admitting a similarity judgement at all: it can only
    excuse a deletion that has an addition to be paired *with*. A wiped disk, a
    failed restore and a stray ``rm -rf`` carry no additions, so git returns no
    pairings and they are held exactly as before."""
    guard = DeletionGuard(share=0.2, floor=20)
    changes = _deletions("knowledge", 40)
    assert guard.breached_areas(changes, {"knowledge": 40}, renames=[]) == [("knowledge", 40, 40)]


def test_a_pairing_names_a_source_the_diff_never_deleted() -> None:
    """A pairing for a path that is not a deletion in this diff excuses
    nothing. The lookup is by the deletion's own path, so a stale or unrelated
    pairing cannot widen the guard."""
    guard = DeletionGuard(share=0.2, floor=20)
    changes = _deletions("knowledge", 30)
    renames = [("knowledge/somewhere-else.md", "knowledge/elsewhere.md")]
    assert guard.breached_areas(changes, {"knowledge": 30}, renames) == [("knowledge", 30, 30)]


def test_lost_paths_leaves_out_what_git_paired() -> None:
    """A hold lists what the round would *remove*. A document that turned up
    under another name was not removed, by either test."""
    summary = DiffSummary.of(
        [
            DocChange("resources/agent/codex.yaml", ChangeStatus.DELETED, blob="a" * 40),
            DocChange("resources/agent/bc0eff32.yaml", ChangeStatus.ADDED, blob="b" * 40),
            DocChange("resources/skill/gone.yaml", ChangeStatus.DELETED, blob="c" * 40),
        ],
        [("resources/agent/codex.yaml", "resources/agent/bc0eff32.yaml")],
    )
    assert summary.lost_paths() == ("resources/skill/gone.yaml",)


def test_a_move_onto_a_path_the_diff_modified_is_still_a_move() -> None:
    """The destination may be an addition or a modification: a relocation that
    lands on a path that already existed still put the content somewhere."""
    guard = DeletionGuard(share=0.2, floor=20)
    changes = [
        DocChange("knowledge/c/d0.md", ChangeStatus.DELETED, blob="a" * 40),
        DocChange("knowledge/c/sources/d0.md", ChangeStatus.MODIFIED, blob="a" * 40),
    ]
    assert guard.breached_areas(changes, {"knowledge": 1}) == []


def test_two_identical_documents_collapsing_into_one_are_both_excused() -> None:
    """Set membership, not a one-to-one matching. The guard protects content,
    and the content of a duplicate is still in the vault."""
    guard = DeletionGuard(share=0.2, floor=20)
    changes = [
        DocChange("knowledge/c/one.md", ChangeStatus.DELETED, blob="a" * 40),
        DocChange("knowledge/c/two.md", ChangeStatus.DELETED, blob="a" * 40),
        DocChange("knowledge/c/merged.md", ChangeStatus.ADDED, blob="a" * 40),
    ]
    assert guard.breached_areas(changes, {"knowledge": 3}) == []


def test_a_move_that_crosses_areas_is_not_a_move() -> None:
    """The guard's unit is the area, so a knowledge document whose bytes turn
    up under ``skills/`` has still left the area the share is measured over."""
    guard = DeletionGuard(share=0.2, floor=20)
    changes = [
        DocChange("knowledge/c/d0.md", ChangeStatus.DELETED, blob="a" * 40),
        DocChange("skills/d0/SKILL.md", ChangeStatus.ADDED, blob="a" * 40),
    ]
    assert guard.breached_areas(changes, {"knowledge": 1}) == [("knowledge", 1, 1)]


def test_one_added_empty_file_cannot_excuse_deleting_every_empty_document() -> None:
    """Every empty file has identical content by construction rather than by
    provenance, so the empty blob never pairs anything."""
    guard = DeletionGuard()
    changes = [
        *(
            DocChange(f"knowledge/c/d{i}.md", ChangeStatus.DELETED, blob=EMPTY_BLOB)
            for i in range(25)
        ),
        DocChange("knowledge/c/placeholder.md", ChangeStatus.ADDED, blob=EMPTY_BLOB),
    ]
    assert guard.breached_areas(changes, {"knowledge": 30}) == [("knowledge", 25, 30)]


def test_a_relayout_beside_a_real_deletion_is_held_for_the_deletion_alone() -> None:
    """The counts and the path list the user is shown are the losses, so 56
    relocations do not pad the 25 deletions the guard actually stopped."""
    guard = DeletionGuard()
    lost = [
        # A content id no addition in this diff carries: these bytes are gone.
        DocChange(f"knowledge/c/gone{i}.md", ChangeStatus.DELETED, blob=f"f{i:039x}")
        for i in range(25)
    ]
    summary = DiffSummary.of([*_relayout(56), *lost])

    assert guard.breached_areas(summary.vault_changes, {"knowledge": 81}) == [("knowledge", 25, 81)]
    assert summary.lost_paths() == tuple(sorted(c.path for c in lost))
    assert len(summary.paths(ChangeStatus.DELETED)) == 81


@pytest.mark.acceptance(
    spec="vault-sync", scenario="the guard trips above a fifth of an area or at twenty documents"
)
def test_the_fixed_guard_trips_above_a_fifth_or_at_twenty() -> None:
    """The guard the daemon actually runs with: no arguments, so the published
    constants — and those constants are the spec's 20% and 20."""
    assert (DEFAULT_DELETION_SHARE, DEFAULT_DELETION_FLOOR) == (0.2, 20)
    guard = DeletionGuard()

    # Exactly a fifth is still an ordinary round.
    assert guard.breached_areas(_deletions("knowledge", 2), {"knowledge": 10}) == []
    # More than a fifth is not.
    assert guard.breached_areas(_deletions("knowledge", 3), {"knowledge": 10}) == [
        ("knowledge", 3, 10)
    ]
    # Twenty from a large area breaches although it is a tiny share of it...
    assert guard.breached_areas(_deletions("knowledge", 20), {"knowledge": 1000}) == [
        ("knowledge", 20, 1000)
    ]
    # ...and nineteen does not.
    assert guard.breached_areas(_deletions("knowledge", 19), {"knowledge": 1000}) == []

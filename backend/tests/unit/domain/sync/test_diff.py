"""What a converge round changes, and the deletion guard over it.

Covers `specs/vault-sync/spec.md` "Applying a diff" and "Safety" (the
oversized-deletion hold), for the pure domain in `coffer.domain.sync.diff`.
"""

from __future__ import annotations

import pytest

from coffer.domain.sync.diff import (
    DEFAULT_DELETION_FLOOR,
    DEFAULT_DELETION_SHARE,
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

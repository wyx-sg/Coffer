"""Properties of the deletion breaker (spec vault-sync "Hold a round that would
lose too much", "Count losses, not deletions").

The example tests in ``test_breaker.py`` pin the boundaries by hand; these
check the same rules over generated areas: the threshold against an integer
oracle (20 files, or more than a fifth of what the area held), areas judged
independently, a move never counted, and more pairings never adding a loss.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from coffer.domain.sync.breaker import (
    FLOOR,
    PathDelta,
    breached,
    losses,
    totals,
)
from coffer.domain.vault.content_ids import EMPTY_BLOB
from coffer.domain.vault.layout import area_of

#: Content areas the breaker counts, and the registry areas it never does.
_AREAS = ("knowledge", "skills", "memory-triggers")
_NOT_COUNTED = ("machines/m.json", "manifest.json", "stray.txt")


def _should_breach(lost: int, total: int) -> bool:
    """The rule in integers: no float can blur the one-fifth boundary."""
    return lost >= FLOOR or total == 0 or 5 * lost > total


def _area_files(area: str, n: int) -> list[str]:
    return [f"{area}/d{i // 7}/f{i}.md" for i in range(n)]


def _gone(paths: list[str]) -> list[PathDelta]:
    return [PathDelta(p, "D", f"blob:{p}") for p in paths]


@st.composite
def _area_and_losses(draw: st.DrawFn) -> tuple[list[str], list[str]]:
    total = draw(st.integers(min_value=1, max_value=120))
    files = _area_files("knowledge", total)
    lost = draw(st.lists(st.sampled_from(files), unique=True, max_size=total))
    return files, lost


@given(_area_and_losses())
def test_an_area_is_held_exactly_when_the_integer_rule_says_so(
    case: tuple[list[str], list[str]],
) -> None:
    files, gone = case
    lost = losses(_gone(gone))
    assert lost == sorted(gone)  # nothing moved, so every deletion is a loss
    got = breached(lost, totals(files))
    if _should_breach(len(gone), len(files)):
        (breach,) = got
        assert (breach.area, breach.lost, breach.total) == ("knowledge", len(gone), len(files))
    else:
        assert got == []


@given(st.integers(100, 600), st.integers(FLOOR - 5, FLOOR + 5))
def test_a_large_area_is_held_at_the_floor_whatever_its_share(total: int, lost: int) -> None:
    """Where a fifth of the area is more than twenty files, the floor decides."""
    files = _area_files("knowledge", total)
    got = breached(losses(_gone(files[:lost])), totals(files))
    assert bool(got) is (lost >= FLOOR)


@given(
    st.dictionaries(
        st.sampled_from(_AREAS),
        st.tuples(st.integers(1, 80), st.integers(0, 80)),
        min_size=1,
    )
)
def test_each_area_is_judged_on_its_own_losses(shape: dict[str, tuple[int, int]]) -> None:
    files: list[str] = []
    gone: list[str] = []
    for area, (total, lost) in shape.items():
        here = _area_files(area, total)
        files += here
        gone += here[: min(lost, total)]
    got = {b.area: (b.lost, b.total) for b in breached(losses(_gone(gone)), totals(files))}
    expected = {
        area: (min(lost, total), total)
        for area, (total, lost) in shape.items()
        if min(lost, total) and _should_breach(min(lost, total), total)
    }
    assert got == expected


@given(st.integers(1, 60), st.integers(0, 60), st.integers(1, 30))
def test_losing_more_never_releases_a_hold(total: int, lost: int, more: int) -> None:
    files = _area_files("skills", total + more)
    before = totals(files)
    fewer = breached(losses(_gone(files[: min(lost, total)])), before)
    extra = breached(losses(_gone(files[: min(lost, total) + more])), before)
    if fewer:
        assert extra, "a hold released by losing more files"


@given(st.integers(1, 40))
def test_a_loss_in_an_area_the_losing_side_never_counted_always_holds(lost: int) -> None:
    gone = _area_files("memory-triggers", lost)
    (breach,) = breached(losses(_gone(gone)), totals(_area_files("knowledge", 50)))
    assert (breach.area, breach.lost, breach.total) == ("memory-triggers", lost, 0)


@given(st.lists(st.sampled_from(_NOT_COUNTED), min_size=1))
def test_the_registry_the_manifest_and_stray_files_are_never_losses(paths: list[str]) -> None:
    assert losses(_gone(list(dict.fromkeys(paths)))) == []


@st.composite
def _relayout(draw: st.DrawFn) -> list[PathDelta]:
    """An area whose files all move to new folders, bytes unchanged."""
    area = draw(st.sampled_from(_AREAS))
    n = draw(st.integers(1, 80))
    deltas: list[PathDelta] = []
    for i in range(n):
        blob = f"b{i}"
        deltas.append(PathDelta(f"{area}/old/f{i}.md", "D", blob))
        folder = draw(st.sampled_from(("new", "archive", "2026/10")))
        deltas.append(PathDelta(f"{area}/{folder}/f{i}.md", "A", blob))
    return draw(st.permutations(deltas))


@given(_relayout())
def test_a_relayout_inside_one_area_loses_nothing(deltas: list[PathDelta]) -> None:
    assert losses(deltas) == []


@given(st.integers(1, 30), st.sampled_from(_AREAS), st.sampled_from(_AREAS))
def test_bytes_that_land_in_another_area_are_still_a_loss(n: int, src: str, dst: str) -> None:
    deltas = [PathDelta(f"{src}/f{i}.md", "D", f"b{i}") for i in range(n)]
    deltas += [PathDelta(f"{dst}/g{i}.md", "A", f"b{i}") for i in range(n)]
    assert losses(deltas) == ([] if src == dst else sorted(d.path for d in deltas[:n]))


@given(st.integers(1, 30))
def test_an_empty_file_never_pairs_with_another(n: int) -> None:
    deltas = [PathDelta(f"knowledge/e{i}.md", "D", EMPTY_BLOB) for i in range(n)]
    deltas += [PathDelta(f"knowledge/n{i}.md", "A", EMPTY_BLOB) for i in range(n)]
    assert losses(deltas) == sorted(d.path for d in deltas[:n])


@st.composite
def _deltas_and_pairings(
    draw: st.DrawFn,
) -> tuple[list[PathDelta], list[PathDelta], list[tuple[str, str]]]:
    """Deletions, plus extra additions and renames that may pair some of them."""
    deleted = [
        PathDelta(f"{draw(st.sampled_from(_AREAS))}/f{i}.md", "D", f"b{i}")
        for i in range(draw(st.integers(0, 40)))
    ]
    blobs = [d.blob for d in deleted if d.blob] + ["fresh", EMPTY_BLOB]
    added = [
        PathDelta(f"{draw(st.sampled_from(_AREAS))}/n{i}.md", "A", draw(st.sampled_from(blobs)))
        for i in range(draw(st.integers(0, 20)))
    ]
    paths = [d.path for d in deleted] or ["knowledge/none.md"]
    renames = draw(
        st.lists(
            st.tuples(
                st.sampled_from(paths),
                st.sampled_from([f"{a}/moved.md" for a in _AREAS]),
            ),
            max_size=10,
        )
    )
    return deleted, added, renames


@given(_deltas_and_pairings())
def test_a_pairing_only_ever_removes_losses(
    case: tuple[list[PathDelta], list[PathDelta], list[tuple[str, str]]],
) -> None:
    deleted, added, renames = case
    bare = losses(deleted)
    paired = losses(deleted + added, renames=renames)
    assert set(paired) <= set(bare) == {d.path for d in deleted}
    assert paired == sorted(paired)
    for path in set(bare) - set(paired):
        blob = next(d.blob for d in deleted if d.path == path)
        by_bytes = any(
            a.blob == blob and a.blob != EMPTY_BLOB and area_of(a.path) == area_of(path)
            for a in added
        )
        by_git = any(src == path and area_of(dst) == area_of(path) for src, dst in renames)
        assert by_bytes or by_git, f"{path} excused without a same-area pairing"


@given(
    st.dictionaries(
        st.integers(0, 30).map(lambda i: f"resources/skill/r{i}.json"),
        st.integers(0, 30).map(lambda i: f"u{i}"),
        min_size=1,
    ),
    st.sets(st.integers(0, 30).map(lambda i: f"u{i}")),
)
def test_a_resource_is_lost_exactly_when_its_uid_is_gone(
    uids_before: dict[str, str], uids_after: set[str]
) -> None:
    deltas = [PathDelta(p, "D", f"blob:{p}") for p in uids_before]
    got = losses(deltas, uids_before=uids_before, uids_after=uids_after)
    assert got == sorted(p for p, uid in uids_before.items() if uid not in uids_after)

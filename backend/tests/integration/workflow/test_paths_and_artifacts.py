"""The run directory: what the guard refuses, and what the listing attributes.

Integration rather than unit because every one of these touches a real tree —
the guard's job is to keep a write inside it, and a listing's job is to report
what is actually on disk.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.workflow import artifacts, paths
from coffer.infrastructure.workflow.paths import UnsafeWorkflowPath

RUN = "0199c0de4a7b7f0e9b1e3c2d5a6f7081"


# --------------------------------------------------------------------------- #
# The root
# --------------------------------------------------------------------------- #


def test_root_follows_the_override(isolated_workflow_root: pathlib.Path) -> None:
    assert paths.workflow_root() == isolated_workflow_root
    assert paths.run_dir(RUN) == isolated_workflow_root / RUN
    assert paths.catalog_path(RUN).name == "CATALOG.md"
    assert paths.inputs_dir(RUN) == isolated_workflow_root / RUN / "inputs"


def test_root_without_the_override_is_the_real_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hazard itself, pinned: unset, the root is the developer's own tree.

    Asserted with a fake ``$HOME`` so the test states the fallback without
    going anywhere near a real one — and so a future change that made the
    fallback something else has to come here and say so.
    """
    monkeypatch.delenv("COFFER_WORKFLOW_ROOT", raising=False)
    monkeypatch.setenv("HOME", "/tmp/not-a-real-home")

    assert paths.workflow_root() == pathlib.Path("/tmp/not-a-real-home/.coffer/workflows")


# --------------------------------------------------------------------------- #
# The segment guard
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("segment", "reason"),
    [
        ("", "empty path segment"),
        ("..", "traversal segment"),
        (".", "traversal segment"),
        (".hidden", "hidden entries are not addressable"),
        ("a/b", "unsafe segment"),
        # Refused by the hidden-entry rule before the separator is reached —
        # either way it never becomes a path component.
        ("../escape", "hidden entries are not addressable"),
        ("node\\key", "unsafe segment"),
        ("has%3Aescape", "unsafe segment"),
        ("adhoc:task", "unsafe segment"),
    ],
)
def test_guard_refuses_unsafe_segments(segment: str, reason: str) -> None:
    with pytest.raises(UnsafeWorkflowPath) as exc:
        paths.check_segment(segment)
    assert exc.value.reason == reason


def test_guard_accepts_ordinary_and_non_latin_names() -> None:
    for segment in ("draft_td", "td.md", "Tech Design", "设计稿.md", "a-b_c"):
        paths.check_segment(segment)


def test_artifact_name_with_a_separator_is_refused() -> None:
    with pytest.raises(UnsafeWorkflowPath):
        paths.artifact_path(RUN, "draft_td", 1, "../../etc/passwd")


def test_attempt_numbers_start_at_one() -> None:
    with pytest.raises(UnsafeWorkflowPath):
        paths.attempt_dir(RUN, "draft_td", 0)


def test_a_symlinked_node_directory_cannot_carry_a_write_out(
    isolated_workflow_root: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """The guard reads segments; only the resolve check sees a symlink."""
    outside = tmp_path / "outside"
    outside.mkdir()
    node = paths.artifacts_dir(RUN) / "draft_td"
    node.parent.mkdir(parents=True, exist_ok=True)
    node.symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafeWorkflowPath) as exc:
        paths.artifact_path(RUN, "draft_td", 1, "td.md")
    assert exc.value.reason == "escapes the run directory"


# --------------------------------------------------------------------------- #
# Ad-hoc keys on disk
# --------------------------------------------------------------------------- #


def test_adhoc_key_is_encoded_and_decodes_back(isolated_workflow_root: pathlib.Path) -> None:
    """``adhoc:<slug>`` cannot be a directory name, so its colon is escaped."""
    encoded = paths.encode_node_key("adhoc:rerun-the-migration")

    assert encoded == "adhoc%3Arerun-the-migration"
    assert ":" not in encoded
    assert paths.decode_node_dir(encoded) == "adhoc:rerun-the-migration"
    assert paths.node_dir(RUN, "adhoc:rerun-the-migration").name == encoded


def test_a_template_node_key_is_its_own_directory_name() -> None:
    assert paths.encode_node_key("draft_td") == "draft_td"
    assert paths.decode_node_dir("draft_td") == "draft_td"


def test_a_colon_outside_the_adhoc_prefix_is_refused() -> None:
    """Only the one form the layer knows is encoded; the rest is refused."""
    with pytest.raises(UnsafeWorkflowPath):
        paths.encode_node_key("stage:node")
    with pytest.raises(UnsafeWorkflowPath):
        paths.encode_node_key("adhoc:")


# --------------------------------------------------------------------------- #
# Artifacts
# --------------------------------------------------------------------------- #


def test_write_then_read_round_trips(isolated_workflow_root: pathlib.Path) -> None:
    written = artifacts.write_artifact(RUN, "draft_td", 1, "td.md", "# Tech Design\n")

    assert written.read_text(encoding="utf-8") == "# Tech Design\n"
    assert artifacts.read_artifact(RUN, "draft_td", 1, "td.md") == b"# Tech Design\n"
    assert written.parent == paths.attempt_dir(RUN, "draft_td", 1)


def test_ensure_run_dirs_creates_the_two_fixed_children(
    isolated_workflow_root: pathlib.Path,
) -> None:
    run = artifacts.ensure_run_dirs(RUN)

    assert (run / "inputs").is_dir()
    assert (run / "artifacts").is_dir()


def test_listing_attributes_every_artifact_to_its_node_and_attempt(
    isolated_workflow_root: pathlib.Path,
) -> None:
    """FR-031: the catalogue's facts come from where the file is."""
    artifacts.write_artifact(RUN, "draft_td", 1, "td.md", "first try")
    artifacts.write_artifact(RUN, "draft_td", 2, "td.md", "second try, longer")
    artifacts.write_artifact(RUN, "adhoc:rerun-migration", 1, "notes.md", "ran it")

    entries = artifacts.list_artifacts(RUN)

    assert [(e.node_key, e.attempt, e.name) for e in entries] == [
        ("adhoc:rerun-migration", 1, "notes.md"),
        ("draft_td", 1, "td.md"),
        ("draft_td", 2, "td.md"),
    ]
    assert [e.path for e in entries] == [
        "adhoc%3Arerun-migration/1/notes.md",
        "draft_td/1/td.md",
        "draft_td/2/td.md",
    ]
    assert [e.size for e in entries] == [6, 9, 18]
    assert all(e.modified_at.tzinfo is not None for e in entries)


def test_listing_a_run_with_nothing_written_is_empty(
    isolated_workflow_root: pathlib.Path,
) -> None:
    assert artifacts.list_artifacts(RUN) == []


def test_listing_skips_what_the_layer_did_not_write(
    isolated_workflow_root: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """A directory that is not an attempt number attributes nothing."""
    artifacts.write_artifact(RUN, "draft_td", 1, "td.md", "real")
    stray = paths.node_dir(RUN, "draft_td") / "scratch"
    stray.mkdir()
    (stray / "leftover.md").write_text("not an artifact", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere.md"
    elsewhere.write_text("someone else's file", encoding="utf-8")
    (paths.attempt_dir(RUN, "draft_td", 1) / "linked.md").symlink_to(elsewhere)

    entries = artifacts.list_artifacts(RUN)

    assert [(e.node_key, e.attempt, e.name) for e in entries] == [("draft_td", 1, "td.md")]


@pytest.mark.acceptance(spec="workflow", scenario="a run's artifacts become a knowledge collection")
def test_collect_copies_every_attempt_and_leaves_the_run_alone(
    isolated_workflow_root: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """FR-043 / FR-042: promotion copies out; the run directory is unchanged."""
    artifacts.write_artifact(RUN, "draft_td", 1, "td.md", "first")
    artifacts.write_artifact(RUN, "draft_td", 2, "td.md", "second")
    artifacts.write_artifact(RUN, "adhoc:fix", 1, "notes.md", "n")
    destination = tmp_path / "collection"

    copied = artifacts.collect_artifacts(RUN, destination)

    assert copied == 3
    assert sorted(p.name for p in destination.iterdir()) == [
        "adhoc-fix-1-notes.md",
        "draft_td-1-td.md",
        "draft_td-2-td.md",
    ]
    # Both attempts survive the copy rather than one overwriting the other.
    assert (destination / "draft_td-1-td.md").read_text(encoding="utf-8") == "first"
    assert (destination / "draft_td-2-td.md").read_text(encoding="utf-8") == "second"
    assert len(artifacts.list_artifacts(RUN)) == 3

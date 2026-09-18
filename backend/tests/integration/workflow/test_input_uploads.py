"""Uploaded inputs on real disk (FR-051), and the guard on a hostile name."""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.workflow import artifacts, inputs, paths


@pytest.fixture(autouse=True)
def _run_tree(isolated_workflow_root: pathlib.Path) -> None:
    artifacts.ensure_run_dirs("run-1")


@pytest.mark.acceptance(
    spec="workflow", scenario="a run is created from a template and a title alone"
)
def test_the_run_tree_includes_a_workspace_coffer_made() -> None:
    # FR-053: nobody was asked for a working directory; the run has one anyway.
    assert paths.workspace_dir("run-1").is_dir()
    assert paths.inputs_dir("run-1").is_dir()
    assert paths.artifacts_dir("run-1").is_dir()


@pytest.mark.acceptance(
    spec="workflow", scenario="an uploaded file becomes an input the nodes can read"
)
def test_an_upload_lands_under_the_runs_input_directory_and_reports_its_size() -> None:
    ref, size, path = inputs.write_input("run-1", "prd.pdf", b"x" * 10)

    assert ref == "prd.pdf"
    assert size == 10
    assert (paths.inputs_dir("run-1") / "prd.pdf").read_bytes() == b"x" * 10
    # FR-051: the third value is what the NODE is told, and it has to be
    # openable from the working directory — which is the run's `workspace/`,
    # not its `inputs/`. So it is absolute, and it points at the real file.
    assert pathlib.Path(path).is_absolute()
    assert pathlib.Path(path).read_bytes() == b"x" * 10


def test_the_ref_is_relative_so_it_carries_no_machine_layout() -> None:
    ref, _size, _path = inputs.write_input("run-1", "prd.pdf", b"x")

    assert not pathlib.PurePosixPath(ref).is_absolute()
    assert "/" not in ref


@pytest.mark.parametrize(
    "hostile",
    [
        "../../.ssh/authorized_keys",
        "subdir/prd.pdf",
        "..\\..\\windows\\system32\\x.dll",
        "/etc/passwd",
    ],
)
def test_a_filename_carrying_a_path_keeps_only_its_name(hostile: str) -> None:
    ref, _size, _path = inputs.write_input("run-1", hostile, b"x")

    assert "/" not in ref
    assert ".." not in ref
    written = paths.inputs_dir("run-1") / ref
    assert written.is_file()
    assert written.resolve().is_relative_to(paths.run_dir("run-1").resolve())


@pytest.mark.parametrize("refused", ["", "..", ".hidden", "..."])
def test_a_name_that_survives_stripping_but_is_still_unsafe_is_refused(refused: str) -> None:
    # Repaired rather than refused would mean inventing a name the developer
    # did not upload.
    with pytest.raises(paths.UnsafeWorkflowPath):
        inputs.write_input("run-1", refused, b"x")


def test_a_second_upload_of_a_taken_name_gets_its_own_file() -> None:
    first, _, _ = inputs.write_input("run-1", "prd.pdf", b"one")
    second, _, _ = inputs.write_input("run-1", "prd.pdf", b"two", taken=frozenset({first}))

    assert (first, second) == ("prd.pdf", "prd-2.pdf")
    assert (paths.inputs_dir("run-1") / first).read_bytes() == b"one"
    assert (paths.inputs_dir("run-1") / second).read_bytes() == b"two"


def test_deleting_an_upload_removes_its_bytes_and_is_idempotent() -> None:
    ref, _size, _path = inputs.write_input("run-1", "prd.pdf", b"x")

    inputs.delete_input("run-1", ref)
    inputs.delete_input("run-1", ref)

    assert not (paths.inputs_dir("run-1") / ref).exists()


def test_deleting_through_a_traversing_ref_is_refused() -> None:
    with pytest.raises(paths.UnsafeWorkflowPath):
        inputs.delete_input("run-1", "../../CATALOG.md")


def test_a_symlink_out_of_the_run_is_refused_rather_than_followed(
    tmp_path: pathlib.Path,
) -> None:
    # Nothing in this module ever creates one, so a link under ``inputs/``
    # came from somewhere else and its target is not the run's to touch.
    target = tmp_path / "somebody-elses.txt"
    target.write_text("precious", encoding="utf-8")
    link = paths.inputs_dir("run-1") / "link.txt"
    link.symlink_to(target)

    with pytest.raises(paths.UnsafeWorkflowPath):
        inputs.delete_input("run-1", "link.txt")

    assert target.read_text(encoding="utf-8") == "precious"

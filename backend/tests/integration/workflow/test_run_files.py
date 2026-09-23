"""Reading one file out of a run's directory, and the paths refused."""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.workflow import artifacts, files, inputs, paths


@pytest.fixture(autouse=True)
def _run_tree(isolated_workflow_root: pathlib.Path) -> None:
    artifacts.ensure_run_dirs("run-1")


@pytest.mark.acceptance(
    spec="workflow", scenario="a file in the run's context can be read from the app"
)
def test_an_uploaded_input_and_an_artifact_are_both_readable() -> None:
    inputs.write_input("run-1", "prd.md", b"the brief\n")
    artifacts.write_artifact("run-1", "draft_td", 1, "td.md", "one buffer table\n")

    uploaded = files.read_file("run-1", "inputs/prd.md")
    produced = files.read_file("run-1", "artifacts/draft_td/1/td.md")

    assert uploaded is not None and uploaded.text == "the brief\n"
    assert uploaded.name == "prd.md"
    assert produced is not None and produced.text == "one buffer table\n"
    assert produced.truncated is False


def test_a_file_that_is_not_there_is_none_rather_than_empty() -> None:
    # Absent and empty are different answers, and a caller that conflated them
    # would show a blank preview for a file that was deleted.
    assert files.read_file("run-1", "artifacts/gone/1/nope.md") is None


def test_a_directory_is_not_a_file() -> None:
    assert files.read_file("run-1", "inputs") is None


def test_a_long_file_comes_back_as_its_head_and_says_so() -> None:
    body = "x" * (files.MAX_PREVIEW_BYTES + 500)
    inputs.write_input("run-1", "huge.log", body.encode())

    found = files.read_file("run-1", "inputs/huge.log")

    assert found is not None
    assert found.truncated is True
    assert found.text is not None and len(found.text) == files.MAX_PREVIEW_BYTES
    # The SIZE is the file's, not the preview's: a reader has to be able to see
    # how much of it they are looking at.
    assert found.size == files.MAX_PREVIEW_BYTES + 500


def test_bytes_that_are_not_text_come_back_with_no_text() -> None:
    inputs.write_input("run-1", "logo.png", b"\x89PNG\r\n\x1a\n\xff\xfe")

    found = files.read_file("run-1", "inputs/logo.png")

    assert found is not None
    assert found.text is None
    assert found.size == 10


@pytest.mark.parametrize(
    "hostile",
    [
        "../../.ssh/authorized_keys",
        "inputs/../../../etc/passwd",
        "/etc/passwd",
        ".hidden",
        "inputs/.hidden",
        "",
        "..",
    ],
)
def test_a_path_that_is_not_this_runs_to_read_is_refused(hostile: str) -> None:
    with pytest.raises(paths.UnsafeWorkflowPath):
        files.read_file("run-1", hostile)


def test_a_symlink_out_of_the_run_is_refused_rather_than_followed(
    tmp_path: pathlib.Path,
) -> None:
    # Nothing in this layer ever creates one, so a link under the run came from
    # somewhere else and its target is not the run's to read.
    secret = tmp_path / "id_rsa"
    secret.write_text("PRIVATE KEY", encoding="utf-8")
    (paths.inputs_dir("run-1") / "link.txt").symlink_to(secret)

    with pytest.raises(paths.UnsafeWorkflowPath):
        files.read_file("run-1", "inputs/link.txt")


# --- the bytes, for an image a note refers to ---------------------------------


def test_an_image_comes_back_as_bytes_with_a_media_type() -> None:
    """What `read_file` refuses to answer for: a screenshot pasted into a note
    has no text and is still the thing the note is about."""
    png = b"\x89PNG\r\n\x1a\n\xff\xfe"
    inputs.write_input("run-1", "pasted.png", png)

    found = files.read_bytes("run-1", "inputs/pasted.png")

    assert found == (png, "image/png")


def test_a_file_whose_type_is_not_recognised_is_served_opaque() -> None:
    """A run's directory holds whatever its agent wrote, and a browser handed
    `text/html` from it would run that file's script against this app."""
    inputs.write_input("run-1", "page.html", b"<script>alert(1)</script>")

    found = files.read_bytes("run-1", "inputs/page.html")

    assert found is not None and found[1] == "application/octet-stream"


def test_an_svg_is_downloaded_rather_than_rendered() -> None:
    """An SVG is a document that can carry script; it is the one image type
    that is not handed back as an image."""
    inputs.write_input("run-1", "diagram.svg", b"<svg/>")

    found = files.read_bytes("run-1", "inputs/diagram.svg")

    assert found is not None and found[1] == "application/octet-stream"


def test_the_bytes_are_capped_like_the_preview() -> None:
    inputs.write_input("run-1", "huge.bin", b"x" * (files.MAX_PREVIEW_BYTES + 500))

    found = files.read_bytes("run-1", "inputs/huge.bin")

    assert found is not None and len(found[0]) == files.MAX_PREVIEW_BYTES


def test_the_bytes_route_guards_the_same_paths() -> None:
    assert files.read_bytes("run-1", "inputs/gone.png") is None
    with pytest.raises(paths.UnsafeWorkflowPath):
        files.read_bytes("run-1", "../../.ssh/id_rsa")

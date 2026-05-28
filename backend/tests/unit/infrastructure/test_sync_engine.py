"""Cross-platform directory link helper."""

from __future__ import annotations

import sys

import pytest

from coffer.domain.skill.binding import LinkMode
from coffer.domain.skill.drift import DriftKind
from coffer.infrastructure.skill.sync_engine import (
    classify_target,
    make_directory_link,
    remove_directory_link,
)


def _master_skill(tmp_path):
    m = tmp_path / "master"
    m.mkdir()
    (m / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\nbody")
    return m


def test_make_link_creates_link(tmp_path):
    master = _master_skill(tmp_path)
    link = tmp_path / "agent" / "x"
    mode = make_directory_link(target=master, link=link)
    assert mode in {LinkMode.SYMLINK, LinkMode.JUNCTION, LinkMode.COPY_FALLBACK}
    assert (link / "SKILL.md").read_text().startswith("---")


def test_make_link_refuses_existing(tmp_path):
    master = _master_skill(tmp_path)
    link = tmp_path / "agent" / "x"
    link.parent.mkdir()
    link.mkdir()
    with pytest.raises(FileExistsError):
        make_directory_link(target=master, link=link)


def test_remove_link_is_idempotent(tmp_path):
    master = _master_skill(tmp_path)
    link = tmp_path / "agent" / "x"
    make_directory_link(target=master, link=link)
    remove_directory_link(link)
    assert not link.exists()
    # Second call no-op
    remove_directory_link(link)


def test_remove_link_preserves_user_replaced_directory(tmp_path):
    """Data-loss guard: a REAL directory at the link path (the user replaced
    our symlink with their own dir — REPLACED_WITH_REGULAR drift, recorded mode
    SYMLINK) must NEVER be rmtree'd. Only a recorded COPY_FALLBACK is ours."""
    link = tmp_path / "agent" / "skill"
    link.mkdir(parents=True)
    (link / "user-file.txt").write_text("precious user content")
    remove_directory_link(link, link_mode=LinkMode.SYMLINK)
    assert link.is_dir()
    assert (link / "user-file.txt").read_text() == "precious user content"
    # Unknown mode is also treated as not-ours.
    remove_directory_link(link, link_mode=None)
    assert (link / "user-file.txt").exists()


def test_remove_link_deletes_recorded_copy_fallback(tmp_path):
    """A real directory Coffer created as a COPY_FALLBACK IS ours to remove."""
    link = tmp_path / "agent" / "skill"
    link.mkdir(parents=True)
    (link / "SKILL.md").write_text("x")
    remove_directory_link(link, link_mode=LinkMode.COPY_FALLBACK)
    assert not link.exists()


def test_classify_target_ok(tmp_path):
    master = _master_skill(tmp_path)
    link = tmp_path / "agent" / "x"
    make_directory_link(target=master, link=link)
    status = classify_target(link=link, expected_master=master)
    if sys.platform == "win32":
        # Either symlink or junction is fine; both are considered OK.
        assert status.drift is None
    else:
        assert status.drift is None


def test_classify_target_missing_link(tmp_path):
    master = _master_skill(tmp_path)
    link = tmp_path / "agent" / "x"
    status = classify_target(link=link, expected_master=master)
    assert status.drift is DriftKind.MISSING_LINK


def test_classify_target_replaced_with_regular(tmp_path):
    master = _master_skill(tmp_path)
    link = tmp_path / "agent" / "x"
    link.parent.mkdir()
    link.mkdir()
    (link / "stub.txt").write_text("not coffer")
    status = classify_target(link=link, expected_master=master)
    assert status.drift is DriftKind.REPLACED_WITH_REGULAR


def test_classify_target_copy_fallback_ok(tmp_path):
    """A copy_fallback binding is a real directory by design — not drift."""
    master = _master_skill(tmp_path)
    link = tmp_path / "agent" / "x"
    link.parent.mkdir()
    link.mkdir()
    (link / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\nbody")
    status = classify_target(link=link, expected_master=master, link_mode=LinkMode.COPY_FALLBACK)
    assert status.drift is None


def test_classify_target_copy_fallback_without_skill_md_is_drift(tmp_path):
    """A copy_fallback target that lost its SKILL.md is tampered."""
    master = _master_skill(tmp_path)
    link = tmp_path / "agent" / "x"
    link.parent.mkdir()
    link.mkdir()
    (link / "stub.txt").write_text("no skill md here")
    status = classify_target(link=link, expected_master=master, link_mode=LinkMode.COPY_FALLBACK)
    assert status.drift is DriftKind.TAMPERED_LINK


def test_classify_target_missing_master(tmp_path):
    nonexistent_master = tmp_path / "no-such-master"
    link = tmp_path / "agent" / "x"
    status = classify_target(link=link, expected_master=nonexistent_master)
    assert status.drift is DriftKind.MISSING_MASTER


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only symlink redirect test")
def test_classify_target_tampered_symlink(tmp_path):
    master = _master_skill(tmp_path)
    other = tmp_path / "other-master"
    other.mkdir()
    link = tmp_path / "agent" / "x"
    link.parent.mkdir()
    link.symlink_to(other, target_is_directory=True)
    status = classify_target(link=link, expected_master=master)
    assert status.drift is DriftKind.TAMPERED_LINK

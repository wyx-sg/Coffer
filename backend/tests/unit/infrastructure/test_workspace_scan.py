"""WorkspaceScan unit coverage — real symlinks over tmp_path.

The scanner only builds ``ScanEntry`` values; classification rules are the
domain's (``coffer.domain.skill.scan.classify``). The pairs are exercised
together here so the absolute-target invariant ``classify`` depends on is
proven against real filesystem links, not synthetic entries.
"""

from __future__ import annotations

import os
import pathlib

from coffer.domain.skill.scan import classify
from coffer.infrastructure.skill.workspace_scan import WorkspaceScan


def _entry(entries, name):
    return next(e for e in entries if e.name == name)


def test_missing_root_returns_empty(tmp_path):
    assert WorkspaceScan().scan_dir(tmp_path / "nope") == []


def test_file_root_returns_empty(tmp_path):
    f = tmp_path / "afile"
    f.write_text("x")
    assert WorkspaceScan().scan_dir(f) == []


def test_scan_builds_entries_with_absolute_targets(tmp_path):
    master = tmp_path / "master"
    (master / "managed-skill").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    root = tmp_path / "skills"
    root.mkdir()
    # Managed link (absolute target inside master).
    os.symlink(master / "managed-skill", root / "managed-skill")
    # Foreign link via a RELATIVE target — must still resolve to absolute.
    os.symlink(os.path.relpath(elsewhere, root), root / "foreign-rel")
    # Broken link — target never existed; resolve() still yields absolute.
    os.symlink(tmp_path / "ghost", root / "broken")
    # Plain dir + plain file.
    (root / "plain-dir").mkdir()
    (root / "plain.txt").write_text("x")

    entries = WorkspaceScan().scan_dir(root)
    names = [e.name for e in entries]
    assert names == sorted(names)  # deterministic order

    managed = _entry(entries, "managed-skill")
    assert managed.link_target == (master / "managed-skill").resolve()
    foreign = _entry(entries, "foreign-rel")
    assert foreign.link_target is not None and foreign.link_target.is_absolute()
    assert foreign.link_target == elsewhere.resolve()
    broken = _entry(entries, "broken")
    assert broken.link_target is not None and broken.link_target.is_absolute()
    plain_dir = _entry(entries, "plain-dir")
    assert plain_dir.is_dir and plain_dir.link_target is None
    plain_file = _entry(entries, "plain.txt")
    assert not plain_file.is_dir and plain_file.link_target is None


def test_scan_feeds_classify_correctly(tmp_path):
    """End-to-end with the domain classifier: managed excluded, foreign +
    broken links flagged, plain dir adoptable, plain file + dot excluded."""
    master = (tmp_path / "master").resolve()
    (master / "managed-skill").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    root = tmp_path / "skills"
    root.mkdir()
    os.symlink(master / "managed-skill", root / "managed-skill")
    os.symlink(elsewhere, root / "foreign")
    os.symlink(tmp_path / "ghost", root / "broken")
    (root / "hand-copied").mkdir()
    (root / "notes.txt").write_text("x")
    (root / ".system").mkdir()

    unmanaged = classify(WorkspaceScan().scan_dir(root), master_root=master)
    by_name = {u.name: u for u in unmanaged}
    assert set(by_name) == {"foreign", "broken", "hand-copied"}
    assert by_name["foreign"].foreign_link is True
    assert by_name["broken"].foreign_link is True  # dangling → outside master
    assert by_name["hand-copied"].foreign_link is False
    assert by_name["hand-copied"].path == root / "hand-copied"


def test_symlink_inside_master_subpath_is_managed(tmp_path):
    """A link to a SUBPATH of master still classifies as managed."""
    master = (tmp_path / "master").resolve()
    sub = master / "skillname" / "nested"
    sub.mkdir(parents=True)
    root = tmp_path / "skills"
    root.mkdir()
    os.symlink(sub, root / "weird")
    assert classify(WorkspaceScan().scan_dir(root), master_root=master) == []


def test_entries_are_one_level_only(tmp_path):
    root = tmp_path / "skills"
    nested = root / "outer" / "inner"
    nested.mkdir(parents=True)
    entries = WorkspaceScan().scan_dir(root)
    assert [e.name for e in entries] == ["outer"]
    assert all(isinstance(e.path, pathlib.Path) for e in entries)

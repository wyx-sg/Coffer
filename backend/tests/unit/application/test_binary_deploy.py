"""The frozen daemon's sidecar deployment (spec daemon "Deploy frozen sibling
binaries and back up the vault before migrating").

The desktop shell used to place these binaries in ``~/.coffer/bin``; the daemon
does it now. Each build lands in its own ``<version>/`` directory and the public
names are symlinks into it, so a deploy never overwrites a binary in place and
the previous build stays on disk for a rollback. The staleness rules are the
other part worth pinning — size and a version sentinel, and deliberately not
mtime.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from coffer.application.binary_deploy import (
    DEPLOYED_BINARIES,
    KEEP_VERSIONS,
    _atomic_deploy,
    _flip_symlink,
    _sentinel_for,
    deploy_frozen_sidecars,
    needs_deploy,
    prune_versions,
    retire_unshipped_links,
    versioned_target,
)


def _write(path: Path, content: bytes, *, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _deployed(bin_dir: Path, name: str, version: str, content: bytes) -> Path:
    """A complete deploy of ``name`` at ``version``: file, sentinel, symlink."""
    target = _write(bin_dir / version / name, content)
    _sentinel_for(target).write_text(f"{version}\n")
    _flip_symlink(bin_dir / name, target)
    return target


# --------------------------------------------------------------------------- #
# needs_deploy                                                                 #
# --------------------------------------------------------------------------- #


def test_missing_version_dir_needs_a_deploy(tmp_path: Path) -> None:
    source = _write(tmp_path / "src" / "coffer-mcp-shim", b"binary")
    assert needs_deploy(tmp_path / "bin" / "coffer-mcp-shim", source, "1.0.0") is True


def test_complete_deploy_is_left_alone(tmp_path: Path) -> None:
    """The steady state on every restart after the first: nothing to do."""
    source = _write(tmp_path / "src" / "shim", b"same-bytes", mtime=9000)
    _deployed(tmp_path / "bin", "shim", "1.0.0", b"same-bytes")
    assert needs_deploy(tmp_path / "bin" / "shim", source, "1.0.0") is False


def test_newer_source_mtime_alone_does_not_force_a_deploy(tmp_path: Path) -> None:
    """mtime says when a build was extracted, not what it contains: a reinstall
    of the same release must not re-copy every binary on every start."""
    source = _write(tmp_path / "src" / "shim", b"same-bytes", mtime=9000)
    target = _deployed(tmp_path / "bin", "shim", "1.0.0", b"same-bytes")
    os.utime(target, (1000, 1000))
    assert needs_deploy(tmp_path / "bin" / "shim", source, "1.0.0") is False


def test_size_change_forces_a_deploy(tmp_path: Path) -> None:
    source = _write(tmp_path / "src" / "shim", b"longer-bytes")
    _deployed(tmp_path / "bin", "shim", "1.0.0", b"short")
    assert needs_deploy(tmp_path / "bin" / "shim", source, "1.0.0") is True


def test_version_change_forces_a_deploy_at_equal_size(tmp_path: Path) -> None:
    """Two releases can produce a same-size binary; the new version has no
    directory yet, so it is deployed beside the old one."""
    source = _write(tmp_path / "src" / "shim", b"aaaa")
    _deployed(tmp_path / "bin", "shim", "1.0.0", b"bbbb")
    assert needs_deploy(tmp_path / "bin" / "shim", source, "2.0.0") is True


def test_missing_sentinel_forces_a_deploy(tmp_path: Path) -> None:
    """A copy without its sentinel never completed."""
    source = _write(tmp_path / "src" / "shim", b"aaaa")
    target = _deployed(tmp_path / "bin", "shim", "1.0.0", b"aaaa")
    _sentinel_for(target).unlink()
    assert needs_deploy(tmp_path / "bin" / "shim", source, "1.0.0") is True


def test_link_pointing_elsewhere_forces_a_deploy(tmp_path: Path) -> None:
    """The versioned copy is complete but the public name points at another
    version (a manual rollback the user has since undone): flip it back."""
    source = _write(tmp_path / "src" / "shim", b"aaaa")
    _deployed(tmp_path / "bin", "shim", "2.0.0", b"aaaa")
    _deployed(tmp_path / "bin", "shim", "1.0.0", b"old!")  # link now -> 1.0.0
    assert needs_deploy(tmp_path / "bin" / "shim", source, "2.0.0") is True


def test_legacy_in_place_binary_forces_a_deploy(tmp_path: Path) -> None:
    """An install from before versioned directories: a real file at the public
    name, with its sentinel beside it."""
    source = _write(tmp_path / "src" / "shim", b"aaaa")
    legacy = _write(tmp_path / "bin" / "shim", b"aaaa")
    _sentinel_for(legacy).write_text("1.0.0\n")
    assert needs_deploy(legacy, source, "1.0.0") is True


# --------------------------------------------------------------------------- #
# deploy + symlink flip                                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a frozen daemon deploys its sibling binaries on start",
)
def test_deploy_is_atomic_executable_and_reached_by_the_public_name(tmp_path: Path) -> None:
    source = _write(tmp_path / "src" / "shim", b"payload")
    link = tmp_path / "bin" / "shim"
    target = versioned_target(link, "1.2.3")

    _atomic_deploy(source, target, "1.2.3")
    _flip_symlink(link, target)

    assert target == tmp_path / "bin" / "1.2.3" / "shim"
    assert target.read_bytes() == b"payload"
    assert target.stat().st_mode & stat.S_IXUSR
    assert _sentinel_for(target).read_text().strip() == "1.2.3"
    # The path callers use is unchanged and resolves into the version dir.
    assert link.is_symlink() and os.readlink(link) == "1.2.3/shim"
    assert link.read_bytes() == b"payload"
    # No temp sibling survives — a leftover would be mistaken for a binary by
    # anything globbing the directory.
    assert not (tmp_path / "bin" / "1.2.3" / ".shim.tmp").exists()
    assert not (tmp_path / "bin" / ".shim.link.tmp").exists()


def test_new_version_keeps_the_previous_build_for_rollback(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    old = _deployed(bin_dir, "shim", "1.0.0", b"old-build")
    source = _write(tmp_path / "src" / "shim", b"new-build")

    target = versioned_target(bin_dir / "shim", "2.0.0")
    _atomic_deploy(source, target, "2.0.0")
    _flip_symlink(bin_dir / "shim", target)

    assert (bin_dir / "shim").read_bytes() == b"new-build"
    assert old.read_bytes() == b"old-build", "the previous build is not overwritten"
    # Rollback is pointing the link back — nothing else is needed.
    _flip_symlink(bin_dir / "shim", old)
    assert (bin_dir / "shim").read_bytes() == b"old-build"


def test_flip_replaces_a_legacy_in_place_binary_and_its_sentinel(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    legacy = _write(bin_dir / "shim", b"legacy")
    _sentinel_for(legacy).write_text("0.9.0\n")
    target = _write(bin_dir / "1.0.0" / "shim", b"new")

    _flip_symlink(bin_dir / "shim", target)

    assert (bin_dir / "shim").is_symlink()
    assert (bin_dir / "shim").read_bytes() == b"new"
    assert not _sentinel_for(bin_dir / "shim").exists()


# --------------------------------------------------------------------------- #
# prune                                                                        #
# --------------------------------------------------------------------------- #


def test_prune_keeps_the_newest_versions_and_never_the_one_in_use(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    for i, v in enumerate(("1.0.0", "1.1.0", "1.2.0", "2.0.0")):
        target = _deployed(bin_dir, "shim", v, b"x")
        os.utime(target.parent, (1000 + i, 1000 + i))
    # The user rolled the link back to the OLDEST build.
    _flip_symlink(bin_dir / "shim", bin_dir / "1.0.0" / "shim")
    # Something that is not ours lives under bin too.
    (bin_dir / "notes").mkdir()
    (bin_dir / "notes" / "todo.txt").write_text("keep me")

    removed = prune_versions(bin_dir, keep=KEEP_VERSIONS)

    assert sorted(removed) == ["1.1.0"]
    assert (bin_dir / "1.0.0").is_dir(), "in use via the symlink: kept regardless of age"
    assert (bin_dir / "1.2.0").is_dir() and (bin_dir / "2.0.0").is_dir()
    assert (bin_dir / "notes" / "todo.txt").read_text() == "keep me"


# --------------------------------------------------------------------------- #
# deploy_frozen_sidecars end to end                                            #
# --------------------------------------------------------------------------- #


def _frozen_at(monkeypatch: pytest.MonkeyPatch, bundle: Path, home: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(bundle / "coffer-daemon"))
    monkeypatch.setenv("HOME", str(home))


def test_no_op_when_not_frozen() -> None:
    """A source install already has these on PATH via pip (spec daemon "Install
    the console scripts from source")."""
    assert deploy_frozen_sidecars() == []


def test_frozen_deploy_lands_in_a_version_dir_then_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "bundle"
    for name in DEPLOYED_BINARIES:
        _write(bundle / name, name.encode())
    home = tmp_path / "home"
    _frozen_at(monkeypatch, bundle, home)

    assert deploy_frozen_sidecars(version="1.0.0") == list(DEPLOYED_BINARIES)
    bin_dir = home / ".coffer" / "bin"
    for name in DEPLOYED_BINARIES:
        assert (bin_dir / name).is_symlink()
        assert (bin_dir / name).read_bytes() == name.encode()
        assert (bin_dir / "1.0.0" / name).read_bytes() == name.encode()
    # Second start, nothing changed: nothing deployed, nothing touched.
    assert deploy_frozen_sidecars(version="1.0.0") == []


def test_frozen_upgrade_keeps_the_previous_version_and_prunes_older_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "bundle"
    _write(bundle / "coffer-daemon", b"d")
    _write(bundle / "coffer-mcp-shim", b"s")
    home = tmp_path / "home"
    _frozen_at(monkeypatch, bundle, home)
    bin_dir = home / ".coffer" / "bin"

    for i, v in enumerate(("1.0.0", "1.1.0", "1.2.0")):
        assert deploy_frozen_sidecars(version=v) == ["coffer-daemon", "coffer-mcp-shim"]
        os.utime(bin_dir / v, (1000 + i, 1000 + i))

    assert sorted(d.name for d in bin_dir.iterdir() if d.is_dir()) == ["1.1.0", "1.2.0"]
    assert os.readlink(bin_dir / "coffer-daemon") == "1.2.0/coffer-daemon"


def test_frozen_daemon_running_from_bin_itself_deploys_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI-tarball layout: the user extracted the binaries straight into
    ~/.coffer/bin and runs them from there. Source and target are one file."""
    home = tmp_path / "home"
    bin_dir = home / ".coffer" / "bin"
    for name in DEPLOYED_BINARIES:
        _write(bin_dir / name, name.encode())
    _frozen_at(monkeypatch, bin_dir, home)

    assert deploy_frozen_sidecars(version="1.0.0") == []
    assert not (bin_dir / "1.0.0").exists()
    assert all(not (bin_dir / n).is_symlink() for n in DEPLOYED_BINARIES)


def test_a_binary_missing_from_the_bundle_is_skipped_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "bundle"
    _write(bundle / "coffer-daemon", b"d")
    home = tmp_path / "home"
    _frozen_at(monkeypatch, bundle, home)

    assert deploy_frozen_sidecars(version="1.0.0") == ["coffer-daemon"]


# --------------------------------------------------------------------------- #
# retiring a binary the build no longer ships                                  #
# --------------------------------------------------------------------------- #


def test_the_build_ships_three_binaries() -> None:
    assert DEPLOYED_BINARIES == ("coffer", "coffer-daemon", "coffer-mcp-shim")


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a deploy removes the link of a binary the build no longer ships",
)
def test_a_deploy_removes_the_link_of_a_binary_the_build_no_longer_ships(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    bin_dir = home / ".coffer" / "bin"
    # An earlier build deployed four binaries, coffer-callback among them.
    for name in (*DEPLOYED_BINARIES, "coffer-callback"):
        _deployed(bin_dir, name, "1.0.0", b"old " + name.encode())
    # A regular file under a name the build does not ship is not ours.
    _write(bin_dir / "my-own-tool", b"mine")
    bundle = tmp_path / "bundle"
    for name in DEPLOYED_BINARIES:
        _write(bundle / name, b"new " + name.encode())
    _frozen_at(monkeypatch, bundle, home)

    deploy_frozen_sidecars(version="2.0.0")

    assert not (bin_dir / "coffer-callback").exists()
    assert not (bin_dir / "coffer-callback").is_symlink()
    for name in DEPLOYED_BINARIES:
        assert os.readlink(bin_dir / name) == f"2.0.0/{name}"
    assert (bin_dir / "my-own-tool").read_bytes() == b"mine"


def test_retire_leaves_links_it_cannot_prove_are_its_own(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    _deployed(bin_dir, "coffer-callback", "1.0.0", b"cb")
    elsewhere = _write(tmp_path / "opt" / "tool", b"t")
    os.symlink(elsewhere, bin_dir / "tool")
    # A link into a directory that is not a version directory (no sentinel).
    _write(bin_dir / "plain" / "thing", b"x")
    os.symlink("plain/thing", bin_dir / "thing")

    assert retire_unshipped_links(bin_dir) == ["coffer-callback"]
    assert (bin_dir / "tool").is_symlink()
    assert (bin_dir / "thing").is_symlink()


def test_retire_removes_a_dangling_link_into_a_pruned_version(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    os.symlink("0.9.0/coffer-callback", bin_dir / "coffer-callback")

    assert retire_unshipped_links(bin_dir) == ["coffer-callback"]
    assert not (bin_dir / "coffer-callback").is_symlink()


def test_retire_on_a_missing_bin_dir_is_a_no_op(tmp_path: Path) -> None:
    assert retire_unshipped_links(tmp_path / "absent") == []

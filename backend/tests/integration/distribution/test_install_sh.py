"""The one-line installer never writes through a versioned symlink.

After the first frozen daemon start, ``~/.coffer/bin/<name>`` is a symlink into
``~/.coffer/bin/<version>/`` (spec daemon "Deploy frozen sibling binaries and
back up the history database before migrating"). An installer that ``cp``'d onto that name
would follow the link and overwrite the previous version's binary — the one a
rollback needs. The test runs the script's own ``install_binaries`` function,
extracted from ``install.sh`` rather than restated, so no download is involved.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[4]
_INSTALL_SH = _REPO / "docs-site" / "public" / "install.sh"
_BINARIES = ("coffer", "coffer-daemon", "coffer-mcp-shim", "coffer-seatalk-bridge")


def _function(script: str, name: str) -> str:
    """One top-level shell function's definition, from its opening line to the
    first ``}`` in column 0."""
    match = re.search(rf"^{re.escape(name)}\(\) \{{\n.*?^\}}\n", script, re.S | re.M)
    assert match, f"install.sh has no function {name}()"
    return match.group(0)


def _run_install(src: Path, dest: Path) -> subprocess.CompletedProcess[str]:
    script = _INSTALL_SH.read_text()
    prelude = "".join(_function(script, fn) for fn in ("say", "err", "install_binaries"))
    return subprocess.run(
        ["sh", "-c", f'set -eu\n{prelude}\ninstall_binaries "$1" "$2"', "sh", str(src), str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("sh") is None, reason="install.sh is POSIX sh")
def test_install_replaces_version_symlinks_without_touching_their_targets(tmp_path: Path) -> None:
    dest = tmp_path / "bin"
    previous = dest / "0.1.0"
    previous.mkdir(parents=True)
    for name in _BINARIES:
        (previous / name).write_text(f"old {name}\n")
        (previous / name).chmod(0o755)
        (dest / name).symlink_to(previous / name)

    src = tmp_path / "extracted"
    src.mkdir()
    for name in _BINARIES:
        (src / name).write_text(f"new {name}\n")

    result = _run_install(src, dest)
    assert result.returncode == 0, result.stderr

    for name in _BINARIES:
        # The previous version's binary is exactly as it was.
        assert (previous / name).read_text() == f"old {name}\n"
        # The public name is now the new binary itself, executable.
        public = dest / name
        assert not public.is_symlink()
        assert public.read_text() == f"new {name}\n"
        assert public.stat().st_mode & 0o111
    # No temp sibling is left behind.
    assert sorted(p.name for p in dest.iterdir()) == sorted([*_BINARIES, "0.1.0"])


@pytest.mark.skipif(shutil.which("sh") is None, reason="install.sh is POSIX sh")
def test_install_puts_the_shims_library_folder_beside_it(tmp_path: Path) -> None:
    dest = tmp_path / "bin"
    stale = dest / "coffer-mcp-shim-lib"
    stale.mkdir(parents=True)
    (stale / "old.so").write_text("old")

    src = tmp_path / "extracted"
    (src / "coffer-mcp-shim-lib").mkdir(parents=True)
    (src / "coffer-mcp-shim-lib" / "base_library.zip").write_text("new")
    for name in _BINARIES:
        (src / name).write_text(f"new {name}\n")

    result = _run_install(src, dest)
    assert result.returncode == 0, result.stderr

    lib = dest / "coffer-mcp-shim-lib"
    assert sorted(p.name for p in lib.iterdir()) == ["base_library.zip"]
    assert sorted(p.name for p in dest.iterdir()) == sorted([*_BINARIES, lib.name])


@pytest.mark.skipif(shutil.which("sh") is None, reason="install.sh is POSIX sh")
def test_install_refuses_an_archive_missing_a_binary(tmp_path: Path) -> None:
    src = tmp_path / "extracted"
    src.mkdir()
    (src / "coffer").write_text("new coffer\n")
    dest = tmp_path / "bin"
    dest.mkdir()

    result = _run_install(src, dest)

    assert result.returncode == 1
    assert "binary 'coffer-daemon' not found in archive" in result.stderr


def _run_check_git(path: str, home: Path) -> subprocess.CompletedProcess[str]:
    script = _INSTALL_SH.read_text()
    prelude = "".join(_function(script, fn) for fn in ("warn", "check_git"))
    return subprocess.run(
        # The shell by its full path: PATH is the test's made-up one.
        [shutil.which("sh") or "/bin/sh", "-c", f"set -eu\n{prelude}\ncheck_git"],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": path, "HOME": str(home)},
    )


def _fake_git(directory: Path, answer: str) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    fake = directory / "git"
    fake.write_text(f"#!/bin/sh\n{answer}\n")
    fake.chmod(0o755)
    # awk and the shell's own tools stay reachable beside the fake git.
    return f"{directory}:/usr/bin:/bin"


@pytest.mark.skipif(shutil.which("sh") is None, reason="install.sh is POSIX sh")
@pytest.mark.parametrize(
    ("answer", "warning"),
    [
        ('echo "git version 2.30.1"', "git 2.30 is older than 2.40, which Coffer needs."),
        ("exit 1", "git is installed but did not report a version."),
        ('echo "git version 2.45.0"', None),
        ('echo "git version 3.0.0"', None),
    ],
)
def test_the_installer_warns_about_an_old_or_broken_git_and_never_fails(
    tmp_path: Path, answer: str, warning: str | None
) -> None:
    result = _run_check_git(_fake_git(tmp_path / "gitbin", answer), tmp_path)
    assert result.returncode == 0, result.stderr
    if warning is None:
        assert result.stderr == ""
    else:
        assert warning in result.stderr
        assert "start/install#requirements" in result.stderr


@pytest.mark.skipif(shutil.which("sh") is None, reason="install.sh is POSIX sh")
def test_the_installer_warns_when_git_is_missing(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    # Only the empty directory is searched, so no git can be found; the check
    # itself needs nothing else when there is none.
    result = _run_check_git(str(empty), tmp_path)
    assert result.returncode == 0, result.stderr
    assert "git was not found. Coffer needs git 2.40 or later" in result.stderr

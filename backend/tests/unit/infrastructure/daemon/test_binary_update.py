"""Installing a release's archive over the installer's binaries (spec daemon
"Upgrade the installed binaries from the command line")."""

from __future__ import annotations

import hashlib
import io
import pathlib
import tarfile

import pytest

from coffer.infrastructure.daemon.binary_update import (
    BINARIES,
    UpdateError,
    apply_release,
    archive_name,
    expected_sha256,
)
from coffer.infrastructure.daemon.release_check import Release

_TRIPLE = "aarch64-apple-darwin"
_RELEASE = Release("0.4.0", "v0.4.0", "", None, "u")


def _archive(names: tuple[str, ...] = BINARIES) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in names:
            data = f"#!/bin/sh\necho {name} 0.4.0\n".encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _fetcher(archive: bytes, sums: str):  # type: ignore[no-untyped-def]
    def fetch(url: str, dest: pathlib.Path) -> None:
        assert "/v0.4.0/" in url
        dest.write_bytes(sums.encode() if url.endswith("SHA256SUMS") else archive)

    return fetch


def _installed(dest: pathlib.Path) -> pathlib.Path:
    dest.mkdir()
    (dest / "0.3.0").mkdir()
    for name in BINARIES:
        (dest / "0.3.0" / name).write_text("old")
        (dest / name).symlink_to(f"0.3.0/{name}")
    return dest


@pytest.mark.acceptance(
    spec="daemon", scenario="an update installs the verified archive and restarts the daemon"
)
def test_a_verified_archive_replaces_the_links_and_keeps_the_old_version(
    tmp_path: pathlib.Path,
) -> None:
    archive = _archive()
    sums = f"{hashlib.sha256(archive).hexdigest()}  {archive_name(_TRIPLE)}\nabc  other\n"
    dest = _installed(tmp_path / "bin")
    apply_release(_RELEASE, dest, triple=_TRIPLE, fetch=_fetcher(archive, sums))
    for name in BINARIES:
        assert not (dest / name).is_symlink()
        assert "0.4.0" in (dest / name).read_text()
        assert (dest / name).stat().st_mode & 0o111
        # The rename replaced the link, never the file it pointed at.
        assert (dest / "0.3.0" / name).read_text() == "old"


@pytest.mark.acceptance(
    spec="daemon", scenario="an archive that does not match its checksum installs nothing"
)
def test_a_checksum_mismatch_installs_nothing(tmp_path: pathlib.Path) -> None:
    sums = f"{'0' * 64}  {archive_name(_TRIPLE)}\n"
    dest = _installed(tmp_path / "bin")
    with pytest.raises(UpdateError, match="checksum mismatch"):
        apply_release(_RELEASE, dest, triple=_TRIPLE, fetch=_fetcher(_archive(), sums))
    assert all((dest / name).is_symlink() for name in BINARIES)


def test_an_archive_missing_a_binary_installs_nothing(tmp_path: pathlib.Path) -> None:
    archive = _archive(("coffer",))
    sums = f"{hashlib.sha256(archive).hexdigest()}  {archive_name(_TRIPLE)}\n"
    dest = _installed(tmp_path / "bin")
    with pytest.raises(UpdateError, match="malformed"):
        apply_release(_RELEASE, dest, triple=_TRIPLE, fetch=_fetcher(archive, sums))
    assert all((dest / name).is_symlink() for name in BINARIES)


def test_an_unlisted_archive_is_refused() -> None:
    with pytest.raises(UpdateError, match="not listed"):
        expected_sha256("abc  something-else\n", archive_name(_TRIPLE))

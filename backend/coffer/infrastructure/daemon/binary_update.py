"""Install a release's command-line archive over the installer's binaries (spec
daemon "Upgrade the installed binaries from the command line").

The same steps ``install.sh`` takes, so an update and a fresh install leave the
same files: download ``coffer-cli-<triple>.tar.gz`` and the release's
``SHA256SUMS``, refuse an archive whose SHA-256 is not the one listed, extract
it into a temporary folder, and put each binary over its public name in
``~/.coffer/bin`` by a temporary sibling and a rename — a plain copy would
write through the frozen daemon's symlink into the previous version's folder,
the one a rollback needs. The new daemon deploys itself into its versioned
folder when it starts (``application/binary_deploy.py``).

Nothing in ``~/.coffer/bin`` changes until the archive has verified and every
binary it must carry is there.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import stat
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

import httpx

from coffer.infrastructure.daemon.release_check import Release, asset_url
from coffer.infrastructure.platform.host import HostOs, host_os, os_label

#: What the installer puts in ``~/.coffer/bin``, in the order it does.
BINARIES = ("coffer", "coffer-daemon", "coffer-mcp-shim", "coffer-seatalk-bridge")
CHECKSUMS = "SHA256SUMS"
#: The archive is about 150 MB; anything far past that is not the archive.
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
DOWNLOAD_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class UpdateError(Exception):
    """Why an update installed nothing."""


def host_triple() -> str:
    """The release triple for this machine; only Apple Silicon is published."""
    if host_os() is HostOs.MACOS and platform.machine() in ("arm64", "aarch64"):
        return "aarch64-apple-darwin"
    raise UpdateError(
        f"no release is published for {os_label()} {platform.machine()}; "
        "only macOS on Apple Silicon is"
    )


def archive_name(triple: str) -> str:
    return f"coffer-cli-{triple}.tar.gz"


def expected_sha256(checksums: str, name: str) -> str:
    """The SHA-256 ``SHA256SUMS`` lists for ``name`` (``<hex>  <name>`` lines)."""
    for line in checksums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    raise UpdateError(f"{name} is not listed in the release's {CHECKSUMS}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


Download = Callable[[str, Path], None]


def download(url: str, dest: Path) -> None:
    """Stream ``url`` into ``dest``, bounded in size."""
    written = 0
    with (
        httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client,
        client.stream("GET", url, headers={"User-Agent": "coffer-update"}) as r,
        dest.open("wb") as out,
    ):
        r.raise_for_status()
        for chunk in r.iter_bytes():
            written += len(chunk)
            if written > MAX_ARCHIVE_BYTES:
                raise UpdateError(f"{url} is larger than {MAX_ARCHIVE_BYTES} bytes")
            out.write(chunk)


def _extract(archive: Path, into: Path) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        # The "data" filter refuses absolute paths, `..`, links out of the
        # folder and device files.
        tar.extractall(into, filter="data")


def _install_dir(source: Path, target: Path) -> None:
    """Put the folder ``source`` at ``target`` by a temporary sibling and a rename."""
    tmp = target.with_name(f".{target.name}.install.{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(source, tmp, symlinks=True)
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.exists():
        old = target.with_name(f".{target.name}.old.{os.getpid()}")
        os.replace(target, old)
        shutil.rmtree(old, ignore_errors=True)
    os.replace(tmp, target)


def install_binaries(source: Path, dest: Path) -> None:
    """Put each binary in ``source`` over its public name in ``dest``: copy to a
    temporary sibling, make it executable, rename it over the name (which
    replaces a symlink itself, never its target)."""
    missing = [name for name in BINARIES if not (source / name).is_file()]
    if missing:
        raise UpdateError(f"the archive carries no {', '.join(missing)}; the release is malformed")
    dest.mkdir(parents=True, exist_ok=True)
    for name in BINARIES:
        # A one-folder binary (the shim) keeps its libraries in `<name>-lib`
        # beside it; that folder goes in first, so the executable never runs
        # beside libraries from another build.
        lib = source / f"{name}-lib"
        if lib.is_dir():
            _install_dir(lib, dest / lib.name)
        tmp = dest / f".{name}.install.{os.getpid()}"
        shutil.copyfile(source / name, tmp)
        tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(tmp, dest / name)


def apply_release(
    release: Release,
    dest: Path,
    *,
    triple: str | None = None,
    fetch: Download = download,
) -> None:
    """Download, verify and install ``release``'s archive into ``dest``. Raises
    :class:`UpdateError` (or an ``httpx`` error) with ``dest`` untouched."""
    name = archive_name(triple or host_triple())
    with tempfile.TemporaryDirectory(prefix="coffer-update-") as tmp_dir:
        tmp = Path(tmp_dir)
        archive, sums = tmp / name, tmp / CHECKSUMS
        fetch(asset_url(release.tag, CHECKSUMS), sums)
        fetch(asset_url(release.tag, name), archive)
        want = expected_sha256(sums.read_text("utf-8", errors="replace"), name)
        got = sha256_of(archive)
        if got != want:
            raise UpdateError(
                f"checksum mismatch for {name}: expected {want}, got {got}; nothing was installed"
            )
        unpacked = tmp / "unpacked"
        unpacked.mkdir()
        try:
            _extract(archive, unpacked)
        except (tarfile.TarError, OSError) as exc:
            raise UpdateError(f"could not unpack {name}: {exc}") from exc
        install_binaries(unpacked, dest)


__all__ = [
    "BINARIES",
    "UpdateError",
    "apply_release",
    "archive_name",
    "download",
    "expected_sha256",
    "host_triple",
    "install_binaries",
]

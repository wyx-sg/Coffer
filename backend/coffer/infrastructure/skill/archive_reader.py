"""Unpack a skill archive into a staging directory — refusing it first.

Spec skill-manager "Add skills from an archive". The whole archive is refused,
with every offending entry named, before a single byte is extracted when an
entry:

- has an absolute path (``/x``, ``\\x``, ``C:x``) or a ``..`` segment
  (zip-slip — it would land outside the staging directory);
- is a symlink (its target is chosen by whoever made the archive);
- or when the sizes the archive declares already pass the cap.

Declared sizes are a promise the archive's author makes, so extraction counts
the bytes actually decompressed, entry by entry, and stops the moment the
running total passes the cap — a zip bomb with a lying header is caught there,
still inside the staging directory, which the caller removes.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import stat
import zipfile
import zlib
from dataclasses import dataclass
from typing import BinaryIO

from coffer.domain.skill_source_errors import SkillSourceRejected

#: Entries an archiver adds that are never part of a skill.
_JUNK_PREFIXES = ("__MACOSX/",)
_JUNK_NAMES = frozenset({".DS_Store"})
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
#: More entries than any skill folder has; bounds the work a hostile archive can ask for.
MAX_ENTRIES = 10_000
_CHUNK = 64 * 1024


@dataclass(frozen=True)
class Offender:
    entry: str
    problem: str


def _entry_problem(info: zipfile.ZipInfo) -> str | None:
    name = info.filename
    if name.startswith(("/", "\\")) or _DRIVE_RE.match(name):
        return "absolute_path"
    parts = name.replace("\\", "/").split("/")
    if any(p == ".." for p in parts):
        return "parent_segment"
    mode = info.external_attr >> 16
    if mode and stat.S_ISLNK(mode):
        return "symlink"
    return None


def _entry_past_cap(infos: list[zipfile.ZipInfo], cap: int) -> str:
    """The entry whose declared size takes the running total past ``cap``."""
    total = 0
    for info in infos:
        total += info.file_size
        if total > cap:
            return info.filename
    return infos[-1].filename  # pragma: no cover - only called once the total passes


def _is_junk(name: str) -> bool:
    if name.startswith(_JUNK_PREFIXES):
        return True
    return name.rsplit("/", 1)[-1] in _JUNK_NAMES


def _reject(reason: str, message: str, **details: object) -> SkillSourceRejected:
    return SkillSourceRejected(reason, message, dict(details))


def save_upload(stream: BinaryIO, dest: pathlib.Path, *, cap_bytes: int) -> int:
    """Copy an uploaded archive to ``dest`` in chunks, refusing it past the cap."""
    total = 0
    with dest.open("wb") as out:
        while chunk := stream.read(_CHUNK):
            total += len(chunk)
            if total > cap_bytes:
                raise _reject(
                    "archive_too_large",
                    f"the archive is larger than the {cap_bytes // (1024 * 1024)} MB skill cap",
                    limit_bytes=cap_bytes,
                )
            out.write(chunk)
    return total


def extract_archive(archive: pathlib.Path, dest: pathlib.Path, *, cap_bytes: int) -> None:
    """Check every entry of ``archive``, then extract it under ``dest``.

    Raises :class:`SkillSourceRejected` (``SKILL_INVALID``) naming what is wrong;
    on a refusal during extraction ``dest`` may hold a partial tree, which the
    caller's staging directory takes with it.
    """
    try:
        zf = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError) as exc:
        raise _reject(
            "archive_unreadable", f"the file is not a readable .zip or .skill archive ({exc})"
        ) from exc
    with zf:
        infos = [i for i in zf.infolist() if not _is_junk(i.filename)]
        if len(infos) > MAX_ENTRIES:
            raise _reject(
                "archive_too_many_entries",
                f"the archive holds more than {MAX_ENTRIES} entries",
                limit=MAX_ENTRIES,
            )
        offenders = [
            Offender(i.filename, problem)
            for i in infos
            if (problem := _entry_problem(i)) is not None
        ]
        if offenders:
            names = ", ".join(o.entry for o in offenders)
            raise _reject(
                "archive_unsafe_entries",
                f"the archive holds entries that could write outside it or link elsewhere: {names}",
                offenders=[{"entry": o.entry, "problem": o.problem} for o in offenders],
            )
        declared = sum(i.file_size for i in infos)
        if declared > cap_bytes:
            crossing = _entry_past_cap(infos, cap_bytes)
            raise _reject(
                "size_limit_exceeded",
                f"the archive unpacks to more than the {cap_bytes // (1024 * 1024)} MB skill cap "
                f"(it passes the cap at {crossing})",
                offenders=[{"entry": crossing, "problem": "size_limit"}],
                total_bytes=declared,
                limit_bytes=cap_bytes,
            )
        dest.mkdir(parents=True, exist_ok=True)
        root = dest.resolve()
        written = 0
        for info in infos:
            target = (root / info.filename.replace("\\", "/")).resolve()
            if not target.is_relative_to(root):  # belt and braces over _entry_problem
                raise _reject(
                    "archive_unsafe_entries",
                    f"the archive entry {info.filename} would land outside it",
                    offenders=[{"entry": info.filename, "problem": "parent_segment"}],
                )
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            written = _copy_entry(zf, info, target, written, cap_bytes)


def _copy_entry(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, target: pathlib.Path, written: int, cap: int
) -> int:
    """Decompress one entry to ``target``, counting the running total against the cap.

    An entry whose bytes do not match what the archive declares (a lying size
    header fails its CRC; a truncated stream fails to inflate) or that is
    encrypted is refused by name rather than escaping as a server error.
    """
    try:
        with zf.open(info) as src, target.open("wb") as out:
            while chunk := src.read(_CHUNK):
                written += len(chunk)
                if written > cap:
                    raise _reject(
                        "size_limit_exceeded",
                        f"the archive entry {info.filename} takes the archive past the "
                        f"{cap // (1024 * 1024)} MB skill cap",
                        offenders=[{"entry": info.filename, "problem": "size_limit"}],
                        limit_bytes=cap,
                    )
                out.write(chunk)
    except (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError) as exc:
        raise _reject(
            "archive_unreadable",
            f"the archive entry {info.filename} cannot be read as it declares ({exc})",
            offenders=[{"entry": info.filename, "problem": "corrupt"}],
        ) from exc
    return written


def remove_tree(path: pathlib.Path) -> None:
    """Best-effort removal of a staging directory."""
    shutil.rmtree(path, ignore_errors=True)


__all__ = ["MAX_ENTRIES", "ZipArchiveReader", "extract_archive", "remove_tree", "save_upload"]


class ZipArchiveReader:
    """``ArchiveReaderPort`` over the two functions above."""

    def save_upload(self, stream: BinaryIO, dest: pathlib.Path, *, cap_bytes: int) -> int:
        return save_upload(stream, dest, cap_bytes=cap_bytes)

    def extract(self, archive: pathlib.Path, dest: pathlib.Path, *, cap_bytes: int) -> None:
        extract_archive(archive, dest, cap_bytes=cap_bytes)

"""The retrieval sidecar: a disposable, on-disk cache of section vectors.

Spec knowledge FR-025 draws a hard line: the index lives **outside** the
knowledge root and **outside** ``coffer.db``, at one path the user may delete
at any moment, excluded from export and backup, and it is rebuilt from the
files themselves — never read as authority over them. ``$COFFER_INDEX_ROOT``
overrides that path for tests, mirroring how
``coffer.infrastructure.knowledge.paths`` overrides the knowledge root itself.

**Namespacing** (spec memory FR-052): this module is not knowledge-only —
memory's ``coffer__recall`` rides the same disposable-sidecar rule over a
different corpus (fact files, not knowledge files), and the two must not
share one sidecar file or a rebuild of one would silently discard the
other's vectors. Every path-producing function therefore takes a
``namespace`` (default ``"knowledge"``, kept as the bare, un-suffixed file
name for backward compatibility with installations and tests that predate
memory), and ``SidecarIndex`` remembers which namespace it was loaded for so
``save()`` writes back to the same file it came from.

**Storage format** — newline-delimited JSON (NDJSON) in a single file:

- Line 1 is a header, ``{"format_version": N}``. ``load()`` refuses to trust
  a file whose version it doesn't recognise (or that has no readable header
  at all) and starts from empty instead of guessing at bytes it can't
  interpret — the same posture FR-025 wants for a missing or deleted sidecar.
  A future change to what a record holds bumps ``N`` rather than trying to
  migrate an old shape in place; that is cheap precisely because the file is
  disposable.
- Every following line is one JSON object: one indexed file, carrying the
  freshness stamp (size, mtime, content hash) it was indexed at and its
  section vectors.

NDJSON was chosen over one JSON blob because it degrades the way a disposable
cache should: a process killed mid-write leaves a truncated final line, and
``load()`` simply drops any line it cannot parse — every earlier line is a
complete, independently-parseable record, so damage never spreads backwards
through the file. ``save()`` still rewrites the whole file on every call (this
sidecar serves hundreds of files, not millions — a real WAL would be over-
engineering for it), but it writes to a temp file beside the target and
``Path.replace``s it into place, so a crash mid-``save()`` leaves either the
complete old file or the complete new one, never a half-written one at the
path callers actually read.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from coffer.domain.knowledge.retrieval import IndexedSection

INDEX_ROOT_ENV = "COFFER_INDEX_ROOT"
INDEX_FILE_NAME = "sidecar.ndjson"
FORMAT_VERSION = 1


def index_root() -> pathlib.Path:
    """The directory the sidecar lives in — never the knowledge root itself."""
    override = os.environ.get(INDEX_ROOT_ENV)
    if override:
        return pathlib.Path(override)
    home = pathlib.Path(os.environ.get("HOME", "~")).expanduser()
    return home / ".coffer" / "index"


def _file_name(namespace: str) -> str:
    """The sidecar's file name for ``namespace``.

    ``"knowledge"`` keeps the original bare ``sidecar.ndjson`` — the file an
    installation that predates memory already has on disk — so the default
    call site (``index_path()`` with no argument) is unchanged. Every other
    namespace gets its own suffixed file so two consumers never collide.
    """
    if namespace == "knowledge":
        return INDEX_FILE_NAME
    stem = INDEX_FILE_NAME.removesuffix(".ndjson")
    return f"{stem}-{namespace}.ndjson"


def index_path(namespace: str = "knowledge") -> pathlib.Path:
    """The single sidecar file inside :func:`index_root` for ``namespace``."""
    return index_root() / _file_name(namespace)


@dataclass(frozen=True)
class FileStamp:
    """Enough of a file's on-disk state to tell, without re-embedding it, whether
    its indexed sections are still good: path, size, mtime and a content hash.
    Any editor, channel upload, ``write``, or ``git checkout`` that changes the
    file changes at least one of these (FR-028).
    """

    path: str
    size: int
    mtime_ns: int
    digest: str


def stamp_file(relpath: str, absolute: pathlib.Path) -> FileStamp:
    """The current :class:`FileStamp` of the file at ``absolute``."""
    data = absolute.read_bytes()
    stat = absolute.stat()
    digest = hashlib.sha256(data).hexdigest()
    return FileStamp(path=relpath, size=stat.st_size, mtime_ns=stat.st_mtime_ns, digest=digest)


@dataclass(frozen=True)
class _FileRecord:
    stamp: FileStamp
    sections: tuple[IndexedSection, ...]


def _parse_json_object(line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _record_to_dict(record: _FileRecord) -> dict[str, Any]:
    return {
        "path": record.stamp.path,
        "size": record.stamp.size,
        "mtime_ns": record.stamp.mtime_ns,
        "digest": record.stamp.digest,
        "sections": [
            {"heading": s.heading, "start_line": s.start_line, "vector": list(s.vector)}
            for s in record.sections
        ],
    }


def _record_from_dict(obj: dict[str, Any]) -> _FileRecord:
    path = str(obj["path"])
    stamp = FileStamp(
        path=path,
        size=int(obj["size"]),
        mtime_ns=int(obj["mtime_ns"]),
        digest=str(obj["digest"]),
    )
    sections = tuple(
        IndexedSection(
            path=path,
            heading=str(section["heading"]),
            start_line=int(section["start_line"]),
            vector=tuple(float(x) for x in section["vector"]),
        )
        for section in obj.get("sections", [])
    )
    return _FileRecord(stamp=stamp, sections=sections)


class SidecarIndex:
    """The in-memory form of the sidecar file: one record per indexed path.

    Remembers the ``namespace`` it was built or loaded for, so a caller never
    has to pass it again just to ``save()`` back to the same file — the same
    reason a file handle remembers its own path.
    """

    def __init__(
        self, records: dict[str, _FileRecord] | None = None, *, namespace: str = "knowledge"
    ) -> None:
        self._records: dict[str, _FileRecord] = dict(records) if records else {}
        self._namespace = namespace

    @classmethod
    def load(cls, namespace: str = "knowledge") -> SidecarIndex:
        """Read ``namespace``'s sidecar file, or start empty.

        A missing file, an empty file, a header with an unrecognised (or
        absent) ``format_version``, and a truncated or corrupt line are all
        handled the same way this class must always be safe to call: never
        raise, silently drop what can't be trusted, and rebuild the rest on
        demand (FR-025).
        """
        path = index_path(namespace)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return cls(namespace=namespace)
        lines = text.splitlines()
        if not lines:
            return cls(namespace=namespace)
        header = _parse_json_object(lines[0])
        if header is None or header.get("format_version") != FORMAT_VERSION:
            return cls(namespace=namespace)
        records: dict[str, _FileRecord] = {}
        for line in lines[1:]:
            obj = _parse_json_object(line)
            if obj is None:
                continue
            try:
                record = _record_from_dict(obj)
            except (KeyError, TypeError, ValueError):
                continue
            records[record.stamp.path] = record
        return cls(records, namespace=namespace)

    def save(self) -> None:
        """Write the sidecar atomically: a temp file beside it, then replace."""
        root = index_root()
        root.mkdir(parents=True, exist_ok=True)
        target = index_path(self._namespace)
        lines = [json.dumps({"format_version": FORMAT_VERSION})]
        lines.extend(json.dumps(_record_to_dict(record)) for record in self._records.values())
        tmp = target.with_name(f".{target.name}.tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(target)

    def stamp_of(self, path: str) -> FileStamp | None:
        record = self._records.get(path)
        return record.stamp if record else None

    def is_fresh(self, stamp: FileStamp) -> bool:
        """Whether ``stamp`` (the file's current on-disk state) matches what was indexed."""
        existing = self._records.get(stamp.path)
        return existing is not None and existing.stamp == stamp

    def replace_file(self, stamp: FileStamp, sections: Sequence[IndexedSection]) -> None:
        """Index (or reindex) one file's sections under its current stamp."""
        self._records[stamp.path] = _FileRecord(stamp=stamp, sections=tuple(sections))

    def drop(self, path: str) -> None:
        """Remove one file from the index; a no-op if it was never indexed."""
        self._records.pop(path, None)

    def retain(self, paths: Iterable[str]) -> None:
        """Prune every indexed path not in ``paths`` — used to drop deleted files."""
        keep = set(paths)
        for path in [p for p in self._records if p not in keep]:
            del self._records[path]

    def sections(self) -> tuple[IndexedSection, ...]:
        """Every indexed section, across every file, for :func:`rank` to score."""
        result: list[IndexedSection] = []
        for record in self._records.values():
            result.extend(record.sections)
        return tuple(result)

    def indexed_paths(self) -> frozenset[str]:
        return frozenset(self._records)

    def is_empty(self) -> bool:
        return not self._records


__all__ = [
    "FORMAT_VERSION",
    "INDEX_ROOT_ENV",
    "FileStamp",
    "SidecarIndex",
    "index_path",
    "index_root",
    "stamp_file",
]

"""What one conversion keeps, and what it could not keep (design §5).

:class:`Kept` collects the files a page keeps beside its source (pictures,
diagram sources, the Storage Format itself) under safe, unique names, the
issues the walk ran into, and the ``attachments`` frontmatter records. The
walker asks it; it never touches a disk.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from coffer.domain.knowledge.converter import (
    ASSET_LINK_PREFIX,
    ConversionIssue,
    ConvertedFile,
)

#: A kept file over this size is listed as missing instead (the upload itself
#: is capped at 20 MB; one attachment never takes a quarter of that).
MAX_KEPT_BYTES = 5 * 1024 * 1024

MISSING_KIND = "missing_attachment"
EXTERNAL_EMBED = "external_embed"
EXTERNAL_IMAGE = "external_image"
UNSUPPORTED = "unsupported_macro"
NOT_RENDERED = "not_rendered"

#: Why a file the body names is not kept, in a Markdown export (section 6).
NOT_KEPT_BY_MARKDOWN = "not kept by the Markdown export"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_DASHES = re.compile(r"-{2,}")


def safe_name(name: str) -> str:
    """``name`` with every character outside ``[A-Za-z0-9._-]`` replaced by
    ``-`` and runs of ``-`` collapsed; never empty, never hidden."""
    cleaned = _DASHES.sub("-", _UNSAFE.sub("-", name)).strip("-")
    cleaned = cleaned.lstrip(".")
    return cleaned or "file"


def asset_link(name: str) -> str:
    return f"{ASSET_LINK_PREFIX}{name}"


@dataclass
class Kept:
    """The files, issues and attachment records of one conversion.

    ``attachments`` maps an attachment's original name to its bytes; a name in
    ``listed`` was named by the export without its bytes. ``keep_files`` is
    false for a Markdown export, which has no folder to keep anything in.
    """

    attachments: Mapping[str, bytes] = field(default_factory=dict)
    listed: frozenset[str] = frozenset()
    keep_files: bool = True
    page_title: str = ""
    files: list[ConvertedFile] = field(default_factory=list)
    issues: list[ConversionIssue] = field(default_factory=list)
    records: dict[str, dict[str, object]] = field(default_factory=dict)
    _names: set[str] = field(default_factory=set)
    _by_original: dict[str, str] = field(default_factory=dict)
    _diagrams: int = 0

    # -- names ---------------------------------------------------------------

    def _unique(self, wanted: str) -> str:
        name = safe_name(wanted)
        if name not in self._names:
            self._names.add(name)
            return name
        stem, dot, ext = name.rpartition(".")
        if not dot or not stem:
            stem, ext = name, ""
        n = 2
        while True:
            candidate = f"{stem}-{n}.{ext}" if ext else f"{stem}-{n}"
            if candidate not in self._names:
                self._names.add(candidate)
                return candidate
            n += 1

    def keep(self, wanted: str, data: bytes) -> str:
        """Keep ``data`` under a safe unique name derived from ``wanted``."""
        name = self._unique(wanted)
        self.files.append(ConvertedFile(name=name, data=data))
        return name

    # -- issues --------------------------------------------------------------

    def issue(self, kind: str, name: str, reason: str) -> None:
        found = ConversionIssue(kind=kind, name=name, reason=reason)
        if found not in self.issues:
            self.issues.append(found)

    def _missing(self, original: str, reason: str) -> None:
        self.issue(MISSING_KIND, original, reason)
        self.records.setdefault(original, {"name": original, "status": "missing", "reason": reason})

    # -- attachments ---------------------------------------------------------

    def attachment(
        self, original: str, *, other_page: bool = False, wanted: str = ""
    ) -> str | None:
        """The kept name of the attachment ``original``, keeping it on first
        use; ``None`` (and a ``missing_attachment``) when it cannot be kept."""
        if original in self._by_original:
            return self._by_original[original]
        if not self.keep_files:
            self._missing(original, NOT_KEPT_BY_MARKDOWN)
            return None
        if other_page:
            self._missing(original, "on another page")
            return None
        data = self.attachments.get(original)
        if data is None:
            reason = "listed without its file" if original in self.listed else "not in the export"
            self._missing(original, reason)
            return None
        if len(data) > MAX_KEPT_BYTES:
            self._missing(original, "larger than 5 MB")
            return None
        name = self.keep(wanted or original, data)
        self._by_original[original] = name
        self.records[original] = {
            "name": name,
            "original_name": original,
            "path": asset_link(name),
            "status": "saved",
        }
        return name

    def has_attachment(self, original: str) -> bool:
        return original in self.attachments

    def external_image(self, url: str) -> None:
        reason = "a picture hosted elsewhere; not fetched"
        self.issue(EXTERNAL_IMAGE, url, reason)
        self.records.setdefault(url, {"name": url, "status": "external", "reason": reason})

    # -- diagrams ------------------------------------------------------------

    def diagram(self, ext: str, data: bytes) -> str | None:
        """Keep a diagram source as ``diagram-N.<ext>``; ``None`` (and a
        ``missing_attachment``) in a Markdown export or when too large."""
        self._diagrams += 1
        wanted = f"diagram-{self._diagrams}.{ext}"
        if not self.keep_files:
            self._missing(wanted, NOT_KEPT_BY_MARKDOWN)
            return None
        if len(data) > MAX_KEPT_BYTES:
            self._missing(wanted, "larger than 5 MB")
            return None
        name = self.keep(wanted, data)
        self.records[name] = {
            "name": name,
            "original_name": wanted,
            "path": asset_link(name),
            "status": "saved",
        }
        return name

    def next_diagram_label(self) -> str:
        """A name for a diagram that is not kept (a hosted one)."""
        self._diagrams += 1
        return f"diagram-{self._diagrams}"

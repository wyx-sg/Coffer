"""What one Confluence conversion keeps and reports as it goes.

A conversion is handed the attachments that were downloaded with the page
(by their Confluence file names) and the folder under ``assets/`` its files go
in. Each attachment the page refers to is kept once, under a name safe on every
file system, and linked from the Markdown by ``../assets/<folder>/<name>``;
every other part — an embed, a diagram, a macro — is recorded with how it
ended, so the import's report says exactly what was and was not kept (spec
knowledge "Import a Confluence page as a readable source with its
attachments").
"""

from __future__ import annotations

import posixpath
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import quote

from coffer.domain.knowledge.converter import (
    ITEM_KEPT,
    ITEM_MISSING,
    ConvertedFile,
    ImportItem,
)

#: The largest single attachment kept beside a source.
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024

_UNSAFE = re.compile(r"[^A-Za-z0-9._\-一-鿿ぁ-ヿ]+")


def safe_name(name: str) -> str:
    """A Confluence file name as a file name every machine accepts: spaces and
    anything unsafe become ``-``, never a hidden or empty name."""
    base = posixpath.basename(unicodedata.normalize("NFC", name or "").replace("\\", "/"))
    cleaned = _UNSAFE.sub("-", base).strip("-.") or "attachment"
    return cleaned[:120]


@dataclass
class Context:
    """The state of one page's conversion."""

    folder: str
    attachments: dict[str, bytes] = field(default_factory=dict)
    files: list[ConvertedFile] = field(default_factory=list)
    attachment_items: list[ImportItem] = field(default_factory=list)
    macro_items: list[ImportItem] = field(default_factory=list)
    partial: bool = False
    #: Whether files are kept. A page only *read* (a source written before its
    #: markers were converted) keeps nothing: what would be a file has no link.
    keeps_files: bool = True
    _stored: dict[str, str] = field(default_factory=dict)
    _taken: set[str] = field(default_factory=set)
    _counters: dict[str, int] = field(default_factory=dict)

    def link(self, stored: str) -> str:
        """The relative link from a source under ``sources/`` to a kept file."""
        return f"../assets/{quote(self.folder)}/{quote(stored)}"

    def _free(self, wanted: str) -> str:
        stem, dot, ext = wanted.rpartition(".")
        if not dot:
            stem, ext = wanted, ""
        candidate, n = wanted, 2
        while candidate.lower() in self._taken:
            candidate = f"{stem}-{n}.{ext}" if ext else f"{stem}-{n}"
            n += 1
        self._taken.add(candidate.lower())
        return candidate

    def add_file(self, wanted: str, data: bytes) -> str:
        """Keep a file the conversion made (a diagram's source, the raw page)
        and answer its link; ``""`` when this conversion keeps no files."""
        if not self.keeps_files:
            return ""
        stored = self._free(safe_name(wanted))
        self.files.append(ConvertedFile(stored, data))
        return self.link(stored)

    def next_number(self, kind: str) -> int:
        self._counters[kind] = self._counters.get(kind, 0) + 1
        return self._counters[kind]

    def has(self, name: str) -> bool:
        return name in self._stored or name in self.attachments

    def attachment(self, name: str, *, reason_missing: str) -> str | None:
        """Keep the attachment ``name`` the page refers to and answer its link,
        or record it missing with ``reason_missing`` and answer ``None``.
        Kept once however often the page refers to it."""
        if name in self._stored:
            return self.link(self._stored[name])
        data = self.attachments.get(name) if self.keeps_files else None
        if data is None:
            if not any(i.name == name for i in self.attachment_items):
                self.attachment_items.append(ImportItem(name, ITEM_MISSING, reason_missing))
            return None
        if len(data) > MAX_ATTACHMENT_BYTES:
            self.attachment_items.append(
                ImportItem(name, ITEM_MISSING, f"larger than {MAX_ATTACHMENT_BYTES} bytes")
            )
            return None
        stored = self._free(safe_name(name))
        self._stored[name] = stored
        self.files.append(ConvertedFile(stored, data))
        self.attachment_items.append(
            ImportItem(name, ITEM_KEPT, path=f"../assets/{self.folder}/{stored}")
        )
        return self.link(stored)

    def macro(self, name: str, status: str, reason: str = "", path: str = "") -> None:
        self.macro_items.append(ImportItem(name, status, reason, path))


__all__ = ["MAX_ATTACHMENT_BYTES", "Context", "safe_name"]

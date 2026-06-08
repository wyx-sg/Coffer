"""Pure helpers + ports for the KB pipeline.

Split out of ``pipeline.py`` to keep that module under the file-size ceiling.
These are dependency-light (frontmatter/chunking/path math) and reused by the
service for reads (``read_markdown_body``, ``du_bytes``, ``chunker_for``).
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from coffer.domain.knowledge.document import Document
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.infrastructure.knowledge.chunking import chunk_markdown
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

# A filename's extension, lower-cased, restricted to a safe shape so it can never
# escape ``raw/`` (e.g. ``foo./../../etc``).
_SAFE_EXT = re.compile(r"^\.[A-Za-z0-9]{1,16}$")


class DocumentRepoPort(Protocol):
    """The document-row repo surface used by the KB face (a subset of the
    infrastructure ``DocumentRepo`` plus ``count_chunks``)."""

    async def upsert_document(self, d: Document) -> Document: ...
    async def get_document(self, kind: str, resource_name: str, doc_id: str) -> Document | None: ...
    async def list_documents(
        self, kind: str, resource_name: str, *, limit: int, offset: int
    ) -> list[Document]: ...
    async def count_documents(self, kind: str, resource_name: str) -> int: ...
    async def count_chunks(self, kind: str, resource_name: str) -> int: ...
    async def exists_source(self, kind: str, resource_name: str, source_sha256: str) -> bool: ...
    async def delete_document(self, kind: str, resource_name: str, doc_id: str) -> bool: ...
    async def delete_resource(self, kind: str, resource_name: str) -> int: ...


class KBPaths(Protocol):
    """The on-disk path layout (injected — ``infrastructure.knowledge.paths``)."""

    def kb_dir(self, name: str) -> Path: ...
    def docs_dir(self, name: str) -> Path: ...
    def raw_dir(self, name: str) -> Path: ...
    def doc_path(self, name: str, doc_id: str) -> Path: ...
    def raw_path(self, name: str, doc_id: str, ext: str) -> Path: ...
    def knowledge_root(self) -> Path: ...


@dataclass
class Prepared:
    """The result of converting one uploaded file before it is persisted."""

    doc_id: str
    source_sha256: str
    extension: str
    markdown: str
    title: str
    conversion_engine: str


def mkparent_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def extension_of(filename: str) -> str:
    """A safe lower-cased ``.ext`` (or empty), guarding against path escape."""
    idx = filename.rfind(".")
    if idx == -1:
        return ""
    candidate = filename[idx:].lower()
    return candidate if _SAFE_EXT.match(candidate) else ""


def title_of(markdown: str, fallback: str) -> str:
    """First heading / first non-blank line / ``fallback``."""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:200] or fallback
        if stripped:
            return stripped[:200]
    return fallback


def chunker_for(config: KnowledgeBaseConfig) -> Callable[[str], list[str]]:
    """A markdown-aware chunker closure bound to the KB's chunk params."""

    def _chunk(markdown: str) -> list[str]:
        return chunk_markdown(
            markdown, chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap
        )

    return _chunk


def read_markdown_body(full: str) -> str:
    """The markdown body of a ``docs/<id>.md`` file (frontmatter stripped)."""
    _, body = split_frontmatter(full)
    return body


def du_bytes(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            with contextlib.suppress(OSError):
                total += p.stat().st_size
    return total

"""Document entity for the knowledge_base kind."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Document:
    """A single ingested file's metadata.

    The extracted text is computed on demand from the raw file under
    `~/.coffer/kb/<kb_name>/raw/<id><extension>`; this entity only carries
    metadata.
    """

    id: str
    kb_name: str
    filename: str
    extension: str
    size_bytes: int
    sha256: str
    chunk_count: int
    ingested_at: datetime

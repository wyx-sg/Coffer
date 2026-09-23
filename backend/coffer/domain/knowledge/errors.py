"""Knowledge layer errors.

The layer is a directory of files, so its failure modes are a directory's: a
collection that does not exist, a file that does not exist, a path that tries
to leave the root, and a name already taken. Each carries a code the HTTP
surface maps to a status (``surfaces/http/errors.py``).
"""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class KnowledgeError(CofferError):
    """Base for every knowledge-layer failure."""

    code = "KNOWLEDGE_ERROR"


class CollectionNotFound(KnowledgeError):  # noqa: N818
    code = "KNOWLEDGE_COLLECTION_NOT_FOUND"

    def __init__(self, name: str) -> None:
        super().__init__(f"knowledge collection not found: {name!r}")
        self.name = name


class CollectionExists(KnowledgeError):  # noqa: N818
    code = "KNOWLEDGE_COLLECTION_EXISTS"

    def __init__(self, name: str) -> None:
        super().__init__(f"knowledge collection already exists: {name!r}")
        self.name = name


class KnowledgeFileNotFound(KnowledgeError):  # noqa: N818
    code = "KNOWLEDGE_FILE_NOT_FOUND"

    def __init__(self, path: str) -> None:
        super().__init__(f"knowledge file not found: {path!r}")
        self.path = path


class UnsafeKnowledgePath(KnowledgeError):  # noqa: N818
    """A path that escapes the knowledge root, names a hidden entry, or cannot
    name a document.

    All three are refused rather than silently corrected. The document check
    is here rather than in each caller because "a document lives inside a
    collection, and is not its README" is a property of path construction: it
    is what keeps every write, delete and stamp off the collection itself and
    off the inbox (spec knowledge FR-006).
    """

    code = "KNOWLEDGE_PATH_UNSAFE"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"unsafe knowledge path {path!r}: {reason}")
        self.path = path
        self.reason = reason


class UploadTooLarge(KnowledgeError):  # noqa: N818
    """An ingest upload past the size ceiling (FR-019).

    Refused before any conversion or write is attempted, naming the limit so
    the caller knows exactly what to shrink below.
    """

    code = "KNOWLEDGE_UPLOAD_TOO_LARGE"

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"upload of {size} bytes exceeds the {limit} byte limit")
        self.size = size
        self.limit = limit


class TopicReferencesFile(KnowledgeError):  # noqa: N818
    """A curated document naming another knowledge file (FR-027).

    Refused at the write rather than asked for in the prompt. Document paths are
    chosen by curation and move as the corpus is reorganised, so a file name
    written into prose is a link that rots — 343 of the corpus's 398 internal
    references were already dead when this rule was introduced. A document
    names its subject; the catalogue resolves subjects to paths.
    """

    code = "KNOWLEDGE_TOPIC_REFERENCES_FILE"

    def __init__(self, path: str, reference: str) -> None:
        super().__init__(
            f"topic {path!r} references the file {reference!r}; name the subject, not the file"
        )
        self.path = path
        self.reference = reference


class CurationBoundExceeded(KnowledgeError):  # noqa: N818
    """A curation pass tried to write more files than one pass may (FR-025).

    The bound is what makes a pass *incremental*: one source must never be able
    to trigger a corpus-wide rewrite, however confident the model is.
    """

    code = "KNOWLEDGE_CURATION_BOUND"

    def __init__(self, limit: int) -> None:
        super().__init__(f"a curation pass may write at most {limit} files")
        self.limit = limit

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
    """A path that escapes the knowledge root, or names a hidden entry.

    Hidden entries are refused rather than merely skipped: ``.history/`` holds
    revisions the tidy pass superseded, and handing one back through ``read``
    would answer with content the live file has already replaced.
    """

    code = "KNOWLEDGE_PATH_UNSAFE"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"unsafe knowledge path {path!r}: {reason}")
        self.path = path
        self.reason = reason

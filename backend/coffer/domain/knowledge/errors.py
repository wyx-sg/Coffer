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
    off the inbox (spec knowledge "Guard every path through one module").
    """

    code = "KNOWLEDGE_PATH_UNSAFE"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"unsafe knowledge path {path!r}: {reason}")
        self.path = path
        self.reason = reason


class UploadTooLarge(KnowledgeError):  # noqa: N818
    """An ingest upload past the size ceiling.

    Spec knowledge "Bound uploads and leave nothing behind on failure".

    Refused before any conversion or write is attempted, naming the limit so
    the caller knows exactly what to shrink below.
    """

    code = "KNOWLEDGE_UPLOAD_TOO_LARGE"

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"upload of {size} bytes exceeds the {limit} byte limit")
        self.size = size
        self.limit = limit


class KnowledgeHistoryUnavailable(KnowledgeError):  # noqa: N818
    """No history can be read: git is not installed, or the knowledge root has
    no repository it could create.

    Spec knowledge "Commit every knowledge write naming its writer".
    Writes never fail for this — they are simply not recorded — so only a
    read of the changes feed raises it.
    """

    code = "KNOWLEDGE_HISTORY_UNAVAILABLE"

    def __init__(self, reason: str, details: dict[str, object] | None = None) -> None:
        super().__init__(f"knowledge history is unavailable: {reason}")
        self.reason = reason
        #: With git missing, ``domain.git_handoff.git_missing_details``: the
        #: reason and the install hand-off the page offers beside the error.
        if details:
            self.error_details: dict[str, object] = details


class KnowledgeNotADelete(KnowledgeError):  # noqa: N818
    """A restore-a-delete aimed at a change that deleted nothing, or at a
    version that is not a knowledge change at all — only the deletion of a
    document or of a collection is put back this way (spec knowledge "Undo a
    knowledge delete from its toast")."""

    code = "KNOWLEDGE_NOT_A_DELETE"

    def __init__(self, version: str) -> None:
        super().__init__(f"{version!r} did not delete a document or a collection")
        self.version = version


class KnowledgeRestoreConflict(KnowledgeError):  # noqa: N818
    """Putting a deleted document back would overwrite the file now at its
    path. Refused, naming it; nothing is written."""

    code = "KNOWLEDGE_RESTORE_CONFLICT"

    def __init__(self, version: str, document: str) -> None:
        super().__init__(f"cannot restore {document!r}: a document exists at that path again")
        self.version = version
        self.document = document
        self.error_details: dict[str, object] = {"version": version, "document": document}

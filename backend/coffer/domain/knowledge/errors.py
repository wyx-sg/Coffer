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


class KnowledgeFileConflict(KnowledgeError):  # noqa: N818
    """A document changed on disk after the editor read it.

    Spec knowledge "Save a document edited in the web UI". The save is refused
    and the file left as it is: a person's editor or a curation pass wrote it
    in between, and overwriting that silently would lose their change.
    """

    code = "KNOWLEDGE_FILE_CONFLICT"

    def __init__(
        self, path: str, *, current_body: str | None = None, current_fingerprint: str = ""
    ) -> None:
        super().__init__(f"{path!r} changed on disk since it was opened; your text was not saved")
        self.path = path
        #: What the editor needs to recover without saving over the file (spec
        #: knowledge "Save a document edited in the web UI"): the document as it
        #: is on disk now, so the page can Reload, Compare or Copy my text.
        self.error_details: dict[str, object] = {
            "path": path,
            "saved": False,
            "current_body": current_body,
            "current_fingerprint": current_fingerprint,
        }


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


class KnowledgeCurationHeld(KnowledgeError):  # noqa: N818
    """Curate now was refused because a sync round waits for a person.

    Spec knowledge "Curate on one owner machine only" and vault-sync "Never
    overlap a curation pass and a round": a rewrite is never piled onto the very
    files a person is deciding between. Surfaces map this to 409.
    """

    code = "KNOWLEDGE_CURATION_HELD"

    def __init__(self) -> None:
        super().__init__(
            "curation is held while a sync round waits for you — resolve the conflict "
            "or confirmation in Sync, then run it again"
        )


class KnowledgeHistoryUnavailable(KnowledgeError):  # noqa: N818
    """No history can be read: git is not installed, or the knowledge root has
    no repository it could create.

    Spec knowledge "Keep every document's history and undo a pass as a whole".
    Writes never fail for this — they are simply not recorded — so only the
    history reads raise it.
    """

    code = "KNOWLEDGE_HISTORY_UNAVAILABLE"

    def __init__(self, reason: str, details: dict[str, object] | None = None) -> None:
        super().__init__(f"knowledge history is unavailable: {reason}")
        self.reason = reason
        #: With git missing, ``domain.git_handoff.git_missing_details``: the
        #: reason and the install hand-off the page offers beside the error.
        if details:
            self.error_details: dict[str, object] = details


class KnowledgeVersionNotFound(KnowledgeError):  # noqa: N818
    """A version the history does not hold, or one in which the document named
    does not exist."""

    code = "KNOWLEDGE_VERSION_NOT_FOUND"

    def __init__(self, version: str, path: str | None = None) -> None:
        where = f" of {path!r}" if path else ""
        super().__init__(f"no version {version!r}{where} in the knowledge history")
        self.version = version
        self.path = path


class KnowledgeNotAPass(KnowledgeError):  # noqa: N818
    """An undo aimed at a change that is not a curation pass. Any single
    version is restored instead (spec knowledge "Keep every document's history
    and undo a pass as a whole")."""

    code = "KNOWLEDGE_NOT_A_PASS"

    def __init__(self, version: str) -> None:
        super().__init__(
            f"{version!r} is not a curation pass; restore a document's version instead"
        )
        self.version = version


class KnowledgeUndoConflict(KnowledgeError):  # noqa: N818
    """Undoing a pass would overwrite a later change to one of its documents.

    Refused, naming the document, rather than overwriting what came after
    (spec knowledge "Keep every document's history and undo a pass as a
    whole"). Nothing is written.
    """

    code = "KNOWLEDGE_UNDO_CONFLICT"

    def __init__(
        self, version: str, document: str, later: str, *, handoff: str | None = None
    ) -> None:
        super().__init__(
            f"cannot undo this curation pass: {document!r} has changed since "
            "(undo would overwrite that change)"
        )
        self.version = version
        self.document = document
        self.later = later
        self.error_details: dict[str, object] = {
            "version": version,
            "document": document,
            "later_version": later,
        }
        if handoff is not None:
            # Undoing it by hand while keeping the later edits, as a prompt for
            # the person's agent (application/knowledge/undo_handoff.py).
            self.error_details["handoff"] = {"prompt": handoff}


class KnowledgeNotADelete(KnowledgeError):  # noqa: N818
    """A restore-a-delete aimed at a change that deleted nothing — only the
    deletion of a document or of a collection is put back this way (spec
    knowledge "Restore a deleted collection or document from Recent changes")."""

    code = "KNOWLEDGE_NOT_A_DELETE"

    def __init__(self, version: str) -> None:
        super().__init__(
            f"{version!r} did not delete a document or a collection; "
            "restore a document's version instead"
        )
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

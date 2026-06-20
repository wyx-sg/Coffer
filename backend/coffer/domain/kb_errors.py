"""Knowledge-base kind (spec 006) error classes.

Split out of :mod:`coffer.domain.errors` (which re-exports them, so the
``coffer.domain.errors.X`` import paths keep working) to keep that aggregation
module under the file-size ceiling — mirroring how the credential and chat error
families are organised.
"""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class KBNotFound(CofferError):  # noqa: N818
    code = "KB_NOT_FOUND"

    def __init__(self, kb_name: str) -> None:
        super().__init__(f"knowledge base not found: {kb_name!r}")
        self.kb_name = kb_name


class DocumentNotFound(CofferError):  # noqa: N818
    code = "DOCUMENT_NOT_FOUND"

    def __init__(self, kb_name: str, document_id: str) -> None:
        super().__init__(f"document not found: {kb_name}:{document_id}")
        self.kb_name = kb_name
        self.document_id = document_id


class IngestRejected(CofferError):  # noqa: N818
    code = "INGEST_REJECTED"

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class EngineUnavailable(CofferError):  # noqa: N818
    """A converter library, sqlite-vec, or an embedding provider needed for the
    requested operation is unavailable. The caller degrades (vector→keyword) or
    surfaces a clear per-format error; the daemon stays up."""

    code = "ENGINE_UNAVAILABLE"

    def __init__(self, engine: str, detail: str) -> None:
        super().__init__(f"{engine} engine unavailable: {detail}")
        self.engine = engine
        self.detail = detail


class ReconversionBlocked(CofferError):  # noqa: N818
    """Re-converting a document whose ``source_mode == 'edited'`` is refused so
    hand edits are not clobbered; re-uploading a new source resets it."""

    code = "RECONVERSION_BLOCKED"

    def __init__(self, kb_name: str, document_id: str) -> None:
        super().__init__(
            f"cannot re-convert edited document {kb_name}:{document_id}; "
            "upload a new source file to reset source_mode to 'converted'"
        )
        self.kb_name = kb_name
        self.document_id = document_id


class GrepPatternInvalid(CofferError):  # noqa: N818
    """ripgrep rejected the pattern (exit code 2, e.g. invalid regex). Maps to
    400 — without this an rg failure masquerades as 'no matches'."""

    code = "GREP_PATTERN_INVALID"

    def __init__(self, pattern: str, detail: str) -> None:
        super().__init__(f"grep pattern rejected: {detail}")
        self.pattern = pattern
        self.detail = detail


class SearchModeInvalid(CofferError):  # noqa: N818
    """An explicit search mode the store cannot serve. Maps to 400.

    Raised for ``mode="grep"`` on the passage-search endpoint (grep has its own
    endpoint) and for an explicit mode the store has not enabled — instead of a
    silent rewrite. ``vector`` is the one exception: it degrades to keyword with
    a flagged fallback per the spec.
    """

    code = "SEARCH_MODE_INVALID"

    def __init__(self, mode: str, reason: str) -> None:
        super().__init__(f"search mode {mode!r} rejected: {reason}")
        self.mode = mode
        self.reason = reason

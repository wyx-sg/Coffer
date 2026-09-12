"""Errors raised by the knowledge layer's one external dependency: ripgrep.

What is left here is only what survives a layer with no index: the search
binary can be missing, and a caller's regex can be invalid. The knowledge-base
errors this module once held — ``KBNotFound``, ``DocumentNotFound``,
``IngestRejected``, ``ReconversionBlocked`` — went with ingestion and the
index ([Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)).

Kept in its own module, re-exported by :mod:`coffer.domain.errors`, so that
aggregation module stays under the file-size ceiling.
"""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class EngineUnavailable(CofferError):  # noqa: N818
    """A converter library, sqlite-vec, or an embedding provider needed for the
    requested operation is unavailable. The caller degrades (vector→keyword) or
    surfaces a clear per-format error; the daemon stays up."""

    code = "ENGINE_UNAVAILABLE"

    def __init__(self, engine: str, detail: str) -> None:
        super().__init__(f"{engine} engine unavailable: {detail}")
        self.engine = engine
        self.detail = detail


class GrepPatternInvalid(CofferError):  # noqa: N818
    """ripgrep rejected the pattern (exit code 2, e.g. invalid regex). Maps to
    400 — without this an rg failure masquerades as 'no matches'."""

    code = "GREP_PATTERN_INVALID"

    def __init__(self, pattern: str, detail: str) -> None:
        super().__init__(f"grep pattern rejected: {detail}")
        self.pattern = pattern
        self.detail = detail

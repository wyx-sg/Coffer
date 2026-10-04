"""The error raised when an external converter the knowledge layer needs is missing.

Knowledge is plain files with no index
([Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)); the
one dependency outside the package is a converter backend for an uploaded format.

Kept in its own module, re-exported by :mod:`coffer.domain.errors`, so that
aggregation module stays under the file-size ceiling.
"""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class EngineUnavailable(CofferError):  # noqa: N818
    """An external binary or converter library the requested operation needs is
    unavailable — today, one of MarkItDown's format backends. The
    caller surfaces a clear per-format error; the daemon stays up."""

    code = "ENGINE_UNAVAILABLE"

    def __init__(self, engine: str, detail: str) -> None:
        super().__init__(f"{engine} engine unavailable: {detail}")
        self.engine = engine
        self.detail = detail

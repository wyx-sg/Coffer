"""The memory kind's errors."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class UnsafeMemoryPath(CofferError):  # noqa: N818
    """A path segment that is hidden, all dots, or otherwise unsafe: every
    path built from a request passes this guard before anything is read."""

    code = "MEMORY_UNSAFE_PATH"

    def __init__(self, segment: str, reason: str) -> None:
        super().__init__(f"unsafe memory path segment {segment!r}: {reason}")
        self.segment = segment
        self.reason = reason


class MemoryFileNotFound(CofferError):  # noqa: N818
    """No memory file at that project and name. Maps to 404."""

    code = "MEMORY_FILE_NOT_FOUND"

    def __init__(self, path: str) -> None:
        super().__init__(f"no memory file {path!r}")
        self.path = path


class MemoryFileStale(CofferError):  # noqa: N818
    """The file changed since the caller read it; nothing was written."""

    code = "MEMORY_FILE_STALE"

    def __init__(self, path: str) -> None:
        super().__init__(f"memory file {path!r} changed since it was read")
        self.path = path


__all__ = ["MemoryFileNotFound", "MemoryFileStale", "UnsafeMemoryPath"]

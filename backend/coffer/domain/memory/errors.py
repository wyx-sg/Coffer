"""The one failure mode a memory reader has: it could not parse its source.

Spec memory "Fail a broken reader loudly and in isolation" asks for this to
fail loudly and in isolation — the offending file's
path and the reason, so the surface can say exactly what broke, while
everything else aggregation already holds keeps standing. `CofferError`
(rather than a bare `Exception`, which is how the spec's contract sketches it)
is the base every other domain error in this codebase already uses, and gives
this one the `.code` the HTTP surface needs to map it to a status without a
special case.
"""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class UnreadableMemory(CofferError):  # noqa: N818
    """One agent's native memory file could not be parsed.

    Carries the path and the reason a human (or the surface) needs to see
    what changed in the agent's own format — never raised with a half-parsed
    result attached, and never for more than the one file it names.
    """

    code = "MEMORY_UNREADABLE"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"cannot read memory at {path!r}: {reason}")
        self.path = path
        self.reason = reason


class UnsafeMemoryPath(CofferError):  # noqa: N818
    """A path segment that is hidden, all dots, or otherwise unsafe.

    See "Confine reads to registered agents' memory paths": every path built
    from a source's or a hub entry's contents passes this guard.
    """

    code = "MEMORY_UNSAFE_PATH"

    def __init__(self, segment: str, reason: str) -> None:
        super().__init__(f"unsafe memory path segment {segment!r}: {reason}")
        self.segment = segment
        self.reason = reason


class MemorySyncRunning(CofferError):  # noqa: N818
    """A memory sync was asked for while one runs (spec memory "Sync on an
    interval and on demand")."""

    code = "MEMORY_SYNC_RUNNING"

    def __init__(self) -> None:
        super().__init__("a memory sync is already running")


class MemorySyncNoPreview(CofferError):  # noqa: N818
    """**Write** or **Cancel** with no preview pending (spec memory "Preview
    a first or large sync")."""

    code = "MEMORY_SYNC_NO_PREVIEW"

    def __init__(self) -> None:
        super().__init__("no memory sync preview is pending")

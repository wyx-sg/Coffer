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


class NoteConflict(CofferError):  # noqa: N818
    """A note changed after the editor read it.

    Spec memory "Edit a memory in the web UI or on disk". The save is refused
    and the file left as it is: a distil pass or a person's own editor wrote it
    in between, and overwriting that silently would lose their change. The
    refusal carries the note as it is now, so the editor can recover without a
    second save over it.
    """

    code = "MEMORY_NOTE_CONFLICT"

    def __init__(self, slug: str, *, current_body: str, current_fingerprint: str) -> None:
        super().__init__(f"note {slug!r} changed since it was opened; your text was not saved")
        self.slug = slug
        self.error_details: dict[str, object] = {
            "slug": slug,
            "saved": False,
            "current_body": current_body,
            "current_fingerprint": current_fingerprint,
        }

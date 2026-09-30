"""What this machine last learned about a Git-imported skill's source.

Spec skill-manager "Update a Git-imported skill from its source". A check's
result is an observation made here — when it ran, whether git reached the
repository, what the ref points at now — so it lives in its own table and is
never carried by vault sync; the pin itself (the commit the skill's content
came from) is part of the skill's config and does travel.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime


@dataclass(frozen=True)
class SourceStatus:
    skill_resource_id: int
    checked_at: datetime | None = None
    #: The last check that reached the repository; kept through failures so
    #: an unreachable source can say when it last answered.
    last_success_at: datetime | None = None
    #: git's message from the last check, ``None`` when it succeeded.
    error: str | None = None
    #: The commit the ref pointed at when the last check succeeded.
    latest_commit: str | None = None
    #: Commits after the pin that change the skill's folder, and the files they change.
    commits_ahead: int = 0
    files_changed: int = 0
    #: A commit the user chose Keep mine against; it is not offered again.
    dismissed_commit: str | None = None

    def update_available(self, pinned: str) -> bool:
        """Whether the last successful check found commits worth offering."""
        return (
            self.latest_commit is not None
            and self.latest_commit != pinned
            and self.commits_ahead > 0
            and self.latest_commit != self.dismissed_commit
        )

    def with_(self, **changes: object) -> SourceStatus:
        return replace(self, **changes)  # type: ignore[arg-type]


__all__ = ["SourceStatus"]

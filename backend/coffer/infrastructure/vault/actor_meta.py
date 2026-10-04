"""The commit a daemon-side write makes, naming whom it was for (ADR
every-vault-write-is-a-validated-commit-naming-its-writer).

The service states the audit actor (``coffer.application.resource_actor``);
this maps it onto the writer vocabulary: nobody or ``system`` is the daemon's
own write, ``sync`` a round's, ``agent`` / ``agent:<type>`` an agent's through
a Coffer tool, and anything else a person's through a Coffer surface.
"""

from __future__ import annotations

from coffer.application.resource_actor import current_actor
from coffer.domain.vault.writers import (
    WRITER_AGENT,
    WRITER_DAEMON,
    WRITER_SYNC,
    WRITER_USER,
    CommitMeta,
)


def commit_meta(operation: str, summary: str, actor: str | None = None) -> CommitMeta:
    """``CommitMeta`` for ``operation``, for ``actor`` (default: the stated one)."""
    actor = actor if actor is not None else current_actor()
    agent: str | None = None
    if actor in (None, "", "system", "daemon"):
        writer = WRITER_DAEMON
    elif actor == "sync":
        writer = WRITER_SYNC
    elif actor.startswith("agent"):
        writer = WRITER_AGENT
        agent = actor.split(":", 1)[1] if ":" in actor else None
    else:
        writer = WRITER_USER
    return CommitMeta(
        writer=writer, operation=operation, summary=summary, actor=actor or None, agent=agent
    )


__all__ = ["commit_meta"]

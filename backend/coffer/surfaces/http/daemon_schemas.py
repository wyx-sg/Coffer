"""Daemon schemas — status, residency, token rotation, log records.

Split out of ``schemas.py`` to keep every file under the project's size cap
(see ``.agents/stack.md``). They travel together: everything here is part of
the wire shape of ``/api/v1/daemon/*``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class UpstreamSummary(BaseModel):
    registered: int
    enabled: int
    healthy: int
    unhealthy: int


class DaemonStatusOut(BaseModel):
    status: Literal["starting", "ready", "draining"]
    version: str
    #: The daemon process's ``sys.executable`` — the frozen binary or the
    #: interpreter — so a caller reporting version skew can name the build.
    executable: str
    started_at: datetime
    port: int
    upstream_summary: UpstreamSummary | None = None


class DaemonResidencyOut(BaseModel):
    """Whether the daemon outlives the things that use it, and for how long.

    Two settings, one panel, because they are one question with two halves:
    what starts the daemon, and what ends it. Answering only the first gives a
    process that never leaves; only the second, a ceiling on something nothing
    starts.
    """

    #: False where there is no launchd to install into — the toggle renders
    #: as unavailable rather than as off, which is a different claim.
    login_service_supported: bool
    login_service_installed: bool
    #: Hours of disuse before the daemon stands down; ``null`` means never.
    idle_shutdown_hours: float | None = None


class DaemonResidencyIn(BaseModel):
    login_service_installed: bool
    #: Required, with no default, because ``None`` already means something
    #: here: "never stand down". A caller that meant to flip only the login
    #: service and left this out would turn the idle shutdown off without
    #: saying so, and nothing downstream could tell that apart from an
    #: explicit null.
    idle_shutdown_hours: float | None = Field(
        description="Hours of disuse before standing down; null to never stand down",
    )


class TokenRotationOut(BaseModel):
    token: str = Field(description="New token; clients must re-read daemon.json")


class DaemonLogRecordOut(BaseModel):
    """One record of ``daemon.log``, parsed where possible.

    ``daemon.log`` interleaves several writers — Coffer's own JSON (one object
    per line, every field on it), uvicorn, rich, and the cloudflared child's
    zerolog — so ``record`` carries whatever that line stated, normalised onto
    ``timestamp`` / ``level`` / ``logger`` / ``event``, plus ``continuation``
    for the lines (a traceback, a wrapped message) that belong to this record
    rather than to one of their own. A line no writer's format fits is kept whole as
    ``{"raw": <line>}``. The three lifted fields are what a timeline renders
    without knowing any of that; they are absent on a raw line, which is why
    they are nullable.
    """

    timestamp: str | None = None
    level: str | None = None
    #: The message — the ``event`` field of one of Coffer's own lines, or the
    #: text another writer put after its level.
    event: str | None = None
    record: dict[str, Any]


class DaemonLogListOut(BaseModel):
    records: list[DaemonLogRecordOut]

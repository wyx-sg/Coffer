"""Daemon schemas — status, features, residency, token rotation, log records.

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
    status: Literal["ready", "draining"]
    version: str
    #: The daemon process's ``sys.executable`` — the frozen binary or the
    #: interpreter — so a caller reporting version skew can name the build.
    executable: str
    started_at: datetime
    port: int
    upstream_summary: UpstreamSummary | None = None
    #: The release channel this build carries (spec experimental-features
    #: "Stamp every build with a release channel").
    channel: Literal["stable", "dev"]
    #: Every experimental feature, keyed by its key, and whether it is on. The
    #: web sidebar and the desktop shell read their switches from here.
    features: dict[str, bool]
    #: This machine's id, as ``daemon-config.json`` caches it once the daemon
    #: has derived it from the host at start; ``null`` only before that. Here
    #: rather than only on the sync surface because machine identity is not
    #: sync's: a channel is bound to a machine whether or not ``vault_sync``
    #: is on, and ``/api/v1/sync`` is closed while it is off.
    machine_id: str | None
    #: This machine's display label (the hostname unless the user set one).
    machine_name: str


class FeatureOut(BaseModel):
    """One experimental feature and the layer that decided its state."""

    key: str
    enabled: bool
    #: ``pin`` — ``COFFER_FEATURES``; ``setting`` — this machine's choice in
    #: ``daemon-config.json``; ``channel`` — the build's default.
    source: Literal["pin", "setting", "channel"]


class FeatureListOut(BaseModel):
    channel: Literal["stable", "dev"]
    features: list[FeatureOut]


class FeatureSetIn(BaseModel):
    enabled: bool


class DaemonResidencyOut(BaseModel):
    """Whether the system starts the daemon at login.

    Residency is the login service alone: the daemon never stands down on its
    own, so there is no idle window to report (spec daemon "Change residency
    from the settings page or the command line").
    """

    #: False where there is no launchd to install into — the toggle renders
    #: as unavailable rather than as off, which is a different claim.
    login_service_supported: bool
    login_service_installed: bool


class DaemonResidencyIn(BaseModel):
    login_service_installed: bool


class TokenRotationOut(BaseModel):
    token: str = Field(description="New token; clients must re-read daemon.json")


class DaemonLogRecordOut(BaseModel):
    """One record of ``daemon.log``, parsed where possible.

    ``daemon.log`` interleaves several writers — Coffer's own JSON (one object
    per line, every field on it), uvicorn and rich — so ``record`` carries
    whatever that line stated, normalised onto ``timestamp`` / ``level`` /
    ``logger`` / ``event``, plus ``continuation`` for the lines (a traceback, a
    wrapped message) that belong to this record rather than to one of their
    own. A line no writer's format fits is kept whole as
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

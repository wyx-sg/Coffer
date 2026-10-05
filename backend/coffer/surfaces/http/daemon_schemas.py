"""Daemon schemas — status, features, residency, token rotation, log records.

Split out of ``schemas.py`` to keep every file under the project's size cap
(see ``.agents/stack.md``). They travel together: everything here is part of
the wire shape of ``/api/v1/daemon/*``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from coffer.surfaces.http.handoff_schemas import HandoffOut


class UpstreamSummary(BaseModel):
    registered: int
    enabled: int
    healthy: int
    unhealthy: int


class TaskCrashOut(BaseModel):
    """The most recent background task that ended by raising."""

    task: str
    #: The exception's class name; its message and traceback are in daemon.log.
    error: str
    at: datetime
    #: Whether its owner asked for it to be restarted (a channel adapter, a
    #: periodic worker); ``false`` for a one-off task, which stays gone.
    restarting: bool


class RuntimeHealthOut(BaseModel):
    """The event loop's health and the background tasks' crash count.

    Lag is how late the loop woke a periodic probe, over a rolling window: one
    synchronous call blocking the loop stalls every request, channel and turn
    at once, and this is where that shows. See ``application.runtime``.
    """

    #: The window's 99th-percentile loop lag in milliseconds; null before the
    #: probe's first sample.
    loop_lag_p99_ms: float | None
    loop_lag_max_ms: float | None
    loop_lag_samples: int
    loop_lag_window_seconds: float
    #: Supervised background tasks running now.
    tasks_running: int
    #: Background task crashes since the daemon started.
    task_crashes: int
    last_crash: TaskCrashOut | None = None


class DaemonSetupOut(BaseModel):
    """What a daemon in its setup state is waiting for (spec daemon "Wait in a
    setup state when git is missing or too old")."""

    #: What is missing; git is the one thing a daemon waits for.
    need: Literal["git"]
    #: ``git_missing`` — no git on the daemon's or the login shell's ``PATH``;
    #: ``git_too_old`` — the newest git found is older than ``needed``.
    reason: Literal["git_missing", "git_too_old"]
    #: The version of the newest git found (``2.39``); null when none was.
    found: str | None
    #: The oldest version the vault runs on (``2.40``).
    needed: str
    #: What is wrong, why Coffer needs git and what to do, as the CLI prints it.
    message: str
    #: The chore of installing or updating git, for the person's agent.
    handoff: HandoffOut


class DaemonSetupCheckOut(BaseModel):
    """The answer to Check again: whether git is now there."""

    #: git is now there: restart the daemon and it finishes its normal start.
    ready: bool
    #: What it still waits for; null once ``ready``.
    setup: DaemonSetupOut | None = None


class DaemonStatusOut(BaseModel):
    #: ``setup`` — serving, but waiting for git before it opens the vault;
    #: ``setup`` below says why.
    status: Literal["ready", "draining", "setup"]
    version: str
    #: The daemon process's ``sys.executable`` — the frozen binary or the
    #: interpreter — so a caller reporting version skew can name the build.
    executable: str
    started_at: datetime
    port: int
    upstream_summary: UpstreamSummary | None = None
    #: Every experimental feature, keyed by its key, and whether it is on. The
    #: web sidebar and the desktop shell read their switches from here.
    features: dict[str, bool]
    #: This machine's id, as ``daemon-config.json`` caches it once the daemon
    #: has derived it from the host at start; ``null`` only before that. Here
    #: rather than only on the sync surface because machine identity is not
    #: sync's: a channel is bound to a machine whether or not the vault has a
    #: sync remote.
    machine_id: str | None
    #: This machine's display label (the hostname unless the user set one).
    machine_name: str
    #: The daemon's process id, for the Settings Daemon tab's status line.
    pid: int
    #: The commit a release build was made from (short hash); ``null`` in a build from source.
    commit: str | None = None
    #: Coffer's data folder, written ``~/…`` when it sits under the home folder.
    data_dir: str
    #: How many registered agents carry Coffer's gateway entry; ``null`` while
    #: the composition root has not wired the connection service, or when it
    #: could not be read.
    connected_agents: int | None = None
    #: Loop lag and background task crashes (spec daemon "Report event-loop lag
    #: and background task crashes on the status"). Null only from an app
    #: assembled without the daemon's runtime.
    runtime: RuntimeHealthOut | None = None
    #: What the daemon waits for while ``status`` is ``setup``; null otherwise.
    setup: DaemonSetupOut | None = None


class FeatureOut(BaseModel):
    """One experimental feature and the layer that decided its state."""

    key: str
    enabled: bool
    #: ``pin`` — ``COFFER_FEATURES``; ``setting`` — this machine's choice in
    #: ``daemon-config.json``; ``default`` — off, nothing decided otherwise.
    source: Literal["pin", "setting", "default"]


class FeatureListOut(BaseModel):
    features: list[FeatureOut]


class FeatureSetIn(BaseModel):
    enabled: bool


class DaemonRestartOut(BaseModel):
    """A restart under way (spec daemon "Restart itself on request")."""

    #: The port the successor binds — the configured one, so a saved port
    #: change applies. The page finds the new daemon there and reloads from it.
    port: int


class DaemonUpgradeOut(BaseModel):
    """How to upgrade this Coffer (spec daemon "Hand an upgrade of Coffer to an agent")."""

    #: ``binaries`` (the installer's frozen binaries), ``app`` (the macOS
    #: desktop app) or ``source`` (a source checkout).
    install_method: Literal["binaries", "app", "source"]
    #: The prompt that has the person's agent upgrade it that way.
    handoff: HandoffOut


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
    #: Where the record starts in the file, in bytes: the line's identity. The
    #: file only grows at its end, so it names the same record on every read.
    offset: int
    record: dict[str, Any]
    #: For an ERROR about something outside Coffer (a refused connection, a
    #: name that will not resolve, a file it may not read): the chore of finding
    #: out why, for the person's agent. Null for every other record, a Coffer
    #: internal error included.
    handoff: HandoffOut | None = None


class DaemonLogListOut(BaseModel):
    records: list[DaemonLogRecordOut]
    #: Where the next, older page begins; ``null`` when no older record is left.
    #: Opaque, and bound to the filters it was issued with.
    next_cursor: str | None = None
    #: With ``with_total``: how many records match in the file's recent tail
    #: (the last 512 KB, a bounded read). ``null`` when not asked for.
    total: int | None = None
    #: The tail held more than the count covers, so ``total`` is a floor.
    total_is_floor: bool = False
    #: The absolute path of the file the tail was read from, so the Activity
    #: page can name it and open it with ``POST /fs/open``.
    path: str


class DaemonPortOut(BaseModel):
    """The port of the next start beside the port this daemon answers on.

    ``pending`` is a saved port this daemon is not on: it takes effect at the
    next start (spec daemon "Bind a fixed, settable port"), so until then the page
    says so and the status keeps showing ``bound_port``.
    """

    #: The configured port, or the 38470 default when none is configured.
    port: int
    bound_port: int
    pending: bool


class DaemonPortIn(BaseModel):
    port: int


class VaultUsageOut(BaseModel):
    #: The vault repository (``~/.coffer/vault``), a git repository whether or
    #: not it syncs.
    path: str
    #: The working tree and ``.git`` together.
    bytes: int
    #: Commits on the repository's HEAD; null when it is no repository yet.
    versions: int | None


class LocalContentUsageOut(BaseModel):
    #: The one folder "Open folder" opens.
    folder: str
    locations: list[str]
    bytes: int


class HistoryUsageOut(BaseModel):
    #: The database file holding the records; empty for a non-SQLite database.
    path: str
    #: The database (with its WAL) and the log directory together.
    bytes: int


class CacheUsageOut(BaseModel):
    bytes: int


class StorageSummaryOut(BaseModel):
    """What Coffer keeps on this machine, by kind (Settings > Data)."""

    vault: VaultUsageOut
    local_content: LocalContentUsageOut
    history: HistoryUsageOut
    cache: CacheUsageOut


class CacheClearOut(BaseModel):
    cleared_bytes: int

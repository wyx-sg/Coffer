"""/api/v1/daemon/* routes — status, residency, logs, shutdown, rotate-token."""

from __future__ import annotations

import asyncio
import os
import secrets
import signal
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

import coffer
from coffer import build_channel
from coffer.application.agent.connection_service import AgentConnectionService
from coffer.application.audit_service import AuditService
from coffer.application.features import FeatureService
from coffer.application.log_reader import (
    at_least,
    matches_level,
    parse_log_lines,
    tail_lines,
)
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon import login_service, pid_lock
from coffer.infrastructure.daemon.phase import get_daemon_phase, set_daemon_phase
from coffer.infrastructure.logging.files import log_dir
from coffer.infrastructure.mcp.persistence import MCPServerHealthRepo
from coffer.infrastructure.vault.home import coffer_home, daemon_json_path
from coffer.surfaces.http import daemon_port
from coffer.surfaces.http.agent_dependencies import get_agent_connection_service_optional
from coffer.surfaces.http.auth import require_token, set_active_token
from coffer.surfaces.http.daemon_runtime import runtime_health
from coffer.surfaces.http.dependencies import (
    get_actor,
    get_audit_service,
    get_resource_service_optional,
)
from coffer.surfaces.http.feature_dependencies import (
    build_feature_service,
    get_feature_service_optional,
)
from coffer.surfaces.http.mcp.dependencies import get_health_repo_optional
from coffer.surfaces.http.schemas import (
    DaemonLogListOut,
    DaemonLogRecordOut,
    DaemonResidencyIn,
    DaemonResidencyOut,
    DaemonStatusOut,
    TokenRotationOut,
    UpstreamSummary,
)

router = APIRouter(prefix="/api/v1/daemon", tags=["daemon"])

# Daemon lifecycle phase: owned by infrastructure.daemon.phase (the entry's
# uvicorn server flips it to "draining" the moment shutdown begins, before the
# lifespan's teardown), read here by /status.
__all__ = ["get_daemon_phase", "router", "set_daemon_phase", "set_started_at"]


_STARTED_AT = datetime.now(tz=UTC)


def set_started_at(started_at: datetime) -> None:
    """Override the module-level started_at from daemon.json (set by composition root)."""
    global _STARTED_AT
    _STARTED_AT = started_at


@router.get("/status", response_model=DaemonStatusOut)
async def get_status(
    # Both are the ``*_optional`` seams, not the raising getters: /status is the
    # readiness probe and must answer during startup, before the composition
    # root has published either singleton.
    resource_service: ResourceService | None = Depends(get_resource_service_optional),  # noqa: B008
    health_repo: MCPServerHealthRepo | None = Depends(get_health_repo_optional),  # noqa: B008
    features: FeatureService | None = Depends(get_feature_service_optional),  # noqa: B008
    connection: AgentConnectionService | None = Depends(get_agent_connection_service_optional),  # noqa: B008
) -> DaemonStatusOut:
    phase = get_daemon_phase()
    # An app assembled without create_app has published no service; the
    # status still reports what this build and this machine would decide.
    features = features or build_feature_service()
    upstream_summary: UpstreamSummary | None = None
    if resource_service is not None:
        try:
            resources = await resource_service.list(kind="mcp_server")
            registered = len(resources)
            enabled = sum(1 for r in resources if r.enabled)

            # Compute healthy/unhealthy counts from persisted health state.
            # Only rows with an explicit "healthy" or "failing" status count;
            # servers with no health row or "unknown" contribute to neither.
            healthy = 0
            unhealthy = 0
            # Keyed on the uid, never resolved to a name: this payload is a
            # count of servers, not a list of them, so nothing here is ever
            # read by a human. Resolving would cost a join to produce labels
            # that are immediately thrown away — and would reintroduce the very
            # mismatch this intersection exists to avoid, since the health rows
            # and the resource rows would then have to agree on a label rather
            # than on an identity.
            if health_repo is not None:
                health_by_uid = dict(await health_repo.list_all())
                registered_uids = {r.uid for r in resources}
                for server_uid in registered_uids:
                    st = health_by_uid.get(server_uid)
                    if st == "healthy":
                        healthy += 1
                    elif st == "failing":
                        unhealthy += 1

            upstream_summary = UpstreamSummary(
                registered=registered,
                enabled=enabled,
                healthy=healthy,
                unhealthy=unhealthy,
            )
        except Exception:
            upstream_summary = None
    return DaemonStatusOut(
        status=phase,
        # Sourced from the installed package metadata (coffer.__version__),
        # never a hardcoded literal — so a new app and an old detached daemon
        # it reuses report different versions and the skew is detectable
        # client-side (P2) instead of silently passing.
        version=coffer.__version__,
        # Which build is answering: the frozen binary's path, or the interpreter
        # of a run-from-source daemon. Lets a caller that finds a version
        # mismatch say which daemon it attached to, not merely that one exists.
        executable=sys.executable,
        started_at=_STARTED_AT,
        port=daemon_port.get_port(),
        upstream_summary=upstream_summary,
        features=features.enabled_map(),
        machine_id=daemon_config.read_cached_machine_id(),
        machine_name=daemon_config.read_machine_name(),
        pid=os.getpid(),
        commit=build_channel.COMMIT,
        data_dir=_display_path(coffer_home()),
        connected_agents=await _connected_agents(connection),
        runtime=runtime_health(),
    )


def _display_path(path: Path) -> str:
    """``path`` written ``~/…`` when it sits under the home folder, as the UI shows paths."""
    home = Path(os.environ.get("HOME", "~")).expanduser()
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return str(path)


async def _connected_agents(connection: AgentConnectionService | None) -> int | None:
    """How many agents carry Coffer's gateway entry, or ``None`` when it cannot be told.

    Best-effort like the rest of the probe: it reads each agent's config file,
    and a failure must never turn the readiness answer into an error.
    """
    if connection is None:
        return None
    try:
        return len(await connection.connected_agents())
    except Exception:
        return None


# === shutdown / rotate-token ===


def _daemon_json_path() -> Path:
    return daemon_json_path()


def _schedule_shutdown() -> None:
    """Send SIGTERM to ourselves; the daemon entry's signal handler does the cleanup."""
    os.kill(os.getpid(), signal.SIGTERM)


@router.post(
    "/rotate-token",
    response_model=TokenRotationOut,
    dependencies=[Depends(require_token)],
)
async def rotate_token(
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> TokenRotationOut:
    new_token = secrets.token_urlsafe(32)
    path = _daemon_json_path()
    try:
        info = pid_lock.read(path)
    except (OSError, ValueError, KeyError):
        raise HTTPException(status_code=503, detail="daemon.json missing") from None
    # The same atomic, 0600, unique-staging write the daemon publishes with.
    pid_lock.write(path, replace(info, token=new_token))
    set_active_token(new_token)
    await audit.record(AuditEventType.TOKEN_ROTATED.value, actor=actor)
    return TokenRotationOut(token=new_token)


# === residency: whether the system starts the daemon at login ===
#
# Nothing ends the daemon on its own, so the login service is the whole
# setting. The port of the next start has its own routes
# (daemon_port_routes.py); the CLI stays its escape hatch, because a daemon
# that cannot bind its port serves no route to change it.


def _residency() -> DaemonResidencyOut:
    return DaemonResidencyOut(
        login_service_supported=login_service.is_supported(),
        login_service_installed=login_service.is_installed(),
    )


@router.get("/residency", response_model=DaemonResidencyOut, dependencies=[Depends(require_token)])
async def get_residency() -> DaemonResidencyOut:
    return _residency()


@router.put("/residency", response_model=DaemonResidencyOut, dependencies=[Depends(require_token)])
async def put_residency(
    body: DaemonResidencyIn,
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> DaemonResidencyOut:
    """Install or remove the login service, and say what is true afterwards.

    The change takes effect immediately, because launchd is a different
    process and does not care what this one is doing.
    """
    if login_service.is_supported():
        # `launchctl` and the login-shell PATH probe are blocking subprocess
        # calls; on the event loop they stall every other request for their
        # duration, SSE streams included.
        try:
            await asyncio.to_thread(
                login_service.install if body.login_service_installed else login_service.uninstall
            )
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"login service: {exc}") from None

    after = _residency()
    await audit.record(
        AuditEventType.DAEMON_RESIDENCY_UPDATED.value,
        actor=actor,
        details={"login_service_installed": after.login_service_installed},
    )
    return after


@router.post(
    "/shutdown",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_token)],
)
async def shutdown_daemon() -> Response:
    _schedule_shutdown()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# === daemon log tail ===


def _lift(record: dict[str, Any], key: str) -> str | None:
    """A parsed field as a string, or None when the line did not carry it."""
    return str(record[key]) if key in record else None


@router.get(
    "/logs",
    response_model=DaemonLogListOut,
    # The router itself is unauthenticated so /status can serve as a readiness
    # probe; log contents are not probe material, so this route carries its own
    # token dependency.
    dependencies=[Depends(require_token)],
)
async def list_daemon_logs(
    since: datetime | None = Query(default=None),  # noqa: B008
    errors_only: bool = Query(default=False),
    #: Severity floor: everything at or above it survives. "Errors only" was
    #: the only choice this surface offered, which made a warning — the level
    #: most worth noticing before something breaks — visible only by reading
    #: the whole file. ``errors_only`` stays for callers that already send it.
    level: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    trace_id: str | None = Query(
        default=None,
        description="Only the lines written under this correlation id (a request's or a turn's).",
    ),
) -> DaemonLogListOut:
    """The tail of ``daemon.log``, newest-first — the same record ``coffer log daemon``
    reads, for the human looking at the Activity page.

    The file interleaves several writers' formats (see ``log_reader``); they
    are normalised there onto the same fields, so every row here carries the
    time, level and logger its line actually stated."""
    # The lexical prefilter below only holds while both sides are UTC: the log
    # writes `…Z`, so a `since` carrying `+08:00` would compare as a later
    # string than the very instant it names and cut the window at the top.
    # Normalise here, once, rather than per line. A naive `since` is read as
    # UTC, which is the only clock the log keeps.
    if since is not None:
        since = since.replace(tzinfo=UTC) if since.tzinfo is None else since.astimezone(UTC)
    since_iso = since.isoformat() if since is not None else None
    records: list[DaemonLogRecordOut] = []
    log_file = log_dir() / "daemon.log"
    # Parse oldest-first — a traceback is folded into the record above it —
    # then walk the result backwards to serve the page newest-first.
    for record in reversed(parse_log_lines(tail_lines(log_file))):
        if len(records) >= limit:
            break
        if not matches_level(record, errors_only) or not at_least(record, level):
            continue
        if trace_id is not None and record.get("trace_id") != trace_id:
            continue
        at = str(record.get("timestamp", ""))
        # Cheap prefilter: ISO-8601 sorts lexically, so a string compare
        # is enough and costs no parsing per line.
        if since_iso is not None and at and at < since_iso:
            break
        records.append(
            DaemonLogRecordOut(
                timestamp=_lift(record, "timestamp"),
                level=_lift(record, "level"),
                event=_lift(record, "event"),
                record=record,
            )
        )
    return DaemonLogListOut(records=records, path=str(log_file))

"""/api/v1/daemon/* routes — status, backup, shutdown, rotate-token."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import signal
import sqlite3
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

import coffer
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.surfaces.http.auth import require_token, set_active_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.schemas import (
    BackupResultOut,
    DaemonStatusOut,
    TokenRotationOut,
    UpstreamSummary,
)

# Avoid importing kind-specific modules at module level (Contract 6).
# We access the health repo through the same module-level variable pattern
# used by _get_optional_resource_service below.

router = APIRouter(prefix="/api/v1/daemon", tags=["daemon"])

# Daemon lifecycle phase — written by app.py's lifespan, read by /status.
# Lives here (the reader) so app.py stays under the 400-line guideline and
# daemon_routes no longer needs a circular import of app at request time.
_DaemonPhase = Literal["starting", "ready", "draining"]

_vec_available_cache: bool | None = None


def _vec_available() -> bool:
    """Whether sqlite-vec's vec0 extension loads in this process (cached once).

    Function-local import keeps the knowledge engine out of this module's
    import graph (Contract 6) — surfaces may reach knowledge, but only lazily.
    Availability is fixed for a process lifetime, so we probe once.
    """
    global _vec_available_cache
    if _vec_available_cache is None:
        try:
            from coffer.infrastructure.knowledge.vec_index import VecIndex

            probe = VecIndex(":memory:", dimensions=None, kind="_probe", resource_name="_probe")
            _vec_available_cache = bool(probe.available())
        except Exception:
            _vec_available_cache = False
    return _vec_available_cache


_DAEMON_PHASE: _DaemonPhase = "starting"


def get_daemon_phase() -> _DaemonPhase:
    return _DAEMON_PHASE


def set_daemon_phase(phase: _DaemonPhase) -> None:
    global _DAEMON_PHASE
    _DAEMON_PHASE = phase


_STARTED_AT = datetime.now(tz=UTC)
_PORT = 8000  # set by composition root


def set_port(port: int) -> None:
    global _PORT
    _PORT = port


def get_port() -> int:
    """The port the daemon is serving on (set by the composition root)."""
    return _PORT


def set_started_at(started_at: datetime) -> None:
    """Override the module-level started_at from daemon.json (set by composition root)."""
    global _STARTED_AT
    _STARTED_AT = started_at


def _get_optional_resource_service() -> ResourceService | None:
    """Return resource service if initialised, else None (e.g. during startup)."""
    from coffer.surfaces.http import dependencies as _deps

    return _deps._resource_service


def _get_optional_health_repo() -> Any:
    """Return health repo if initialised, else None (e.g. during startup)."""
    from coffer.surfaces.http import dependencies as _deps

    return _deps._health_repo


@router.get("/status", response_model=DaemonStatusOut)
async def get_status(
    resource_service: ResourceService | None = Depends(_get_optional_resource_service),  # noqa: B008
    health_repo: Any | None = Depends(_get_optional_health_repo),  # noqa: B008
) -> DaemonStatusOut:
    phase = get_daemon_phase()
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
            if health_repo is not None:
                health_rows: list[tuple[str, str]] = await health_repo.list_all()
                health_by_name = dict(health_rows)
                registered_names = {r.name for r in resources}
                for name in registered_names:
                    st = health_by_name.get(name)
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
        started_at=_STARTED_AT,
        port=_PORT,
        upstream_summary=upstream_summary,
        vec_available=_vec_available(),
    )


# === T035: backup / shutdown / rotate-token ===


def _daemon_json_path() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "daemon.json"


def _default_backup_dir() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "backups"


def _default_db_path() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "coffer.db"


def _schedule_shutdown() -> None:
    """Send SIGTERM to ourselves; the daemon entry's signal handler does the cleanup."""
    os.kill(os.getpid(), signal.SIGTERM)


def _atomic_write_0600(target: Path, contents: str) -> None:
    """Write `contents` to `target` atomically with mode 0600.

    Uses O_CREAT|O_EXCL with explicit mode bits so the file never exists
    on-disk with broader-than-0600 permissions (CODE-018: the previous
    pattern of ``write_text`` + ``chmod`` left the file readable by other
    users with a non-restrictive umask for the window between the two calls).
    """
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    # Best-effort: clear any stale tmp from a previous crashed run so O_EXCL
    # below succeeds. The unlink is itself permission-safe.
    import contextlib as _contextlib

    with _contextlib.suppress(FileNotFoundError):
        tmp_path.unlink()
    fd = os.open(
        str(tmp_path),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(contents)
    except Exception:
        # On write failure, remove the partial tmp before re-raising.
        with _contextlib.suppress(FileNotFoundError):
            tmp_path.unlink()
        raise
    os.replace(str(tmp_path), str(target))


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
    if not path.exists():
        raise HTTPException(status_code=503, detail="daemon.json missing")
    info = json.loads(path.read_text())
    info["token"] = new_token
    # Same atomic-replace + 0600 pattern as bootstrap.write. Use the helper
    # so the tmp file never exists with mode wider than 0600 (CODE-018).
    _atomic_write_0600(path, json.dumps(info, indent=2))
    set_active_token(new_token)
    await audit.record(AuditEventType.TOKEN_ROTATED.value, actor=actor)
    return TokenRotationOut(token=new_token)


def _resolve_backup_dest(custom: str | None) -> Path:
    """Resolve the backup destination, blocking obvious file-write abuse.

    Rules (CODE-002):
    - When ``custom`` is None → default to ``~/.coffer/backups/coffer.db.<ts>.bak``.
    - ``..`` in the supplied path is rejected (path traversal).
    - When ``COFFER_BACKUP_STRICT=1`` is set the destination MUST resolve
      under the backup root (``COFFER_BACKUP_DIR`` if set, else
      ``~/.coffer/backups/``). Strict mode is intended for hardened
      deployments; the default mode keeps backwards compatibility with the
      pre-fix behaviour of accepting any user-supplied absolute path the
      authenticated CLI/UI can already write to anyway.

    In every mode we resolve to a canonical absolute Path and ensure the
    parent directory exists before opening the SQLite backup connection.
    """
    override = os.environ.get("COFFER_BACKUP_DIR")
    allowed_root = (
        Path(override).expanduser().resolve() if override else _default_backup_dir().resolve()
    )
    allowed_root.mkdir(parents=True, exist_ok=True)

    if custom is None:
        ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S")
        return allowed_root / f"coffer.db.{ts}.bak"

    # Always reject `..` segments — there's no legitimate reason for a backup
    # client to ask for traversal; this is cheap and covers the most obvious
    # abuse pattern even in non-strict mode.
    if ".." in Path(custom).parts:
        raise HTTPException(
            status_code=400,
            detail="backup path must not contain '..'",
        )

    candidate = Path(custom).expanduser()
    if not candidate.is_absolute():
        candidate = allowed_root / candidate

    if os.environ.get("COFFER_BACKUP_STRICT") == "1":
        resolved_parent = candidate.parent.resolve()
        try:
            resolved_parent.relative_to(allowed_root)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=(f"backup path must be inside {allowed_root}; got parent={resolved_parent}"),
            ) from exc
        return resolved_parent / candidate.name

    return candidate


@router.post(
    "/backup",
    response_model=BackupResultOut,
    dependencies=[Depends(require_token)],
)
async def backup_db(
    body: dict[str, Any] | None = Body(default=None),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> BackupResultOut:
    src = _default_db_path()
    if not src.exists():
        raise HTTPException(status_code=503, detail="coffer.db does not exist")
    custom_raw = (body or {}).get("path") if body else None
    custom = str(custom_raw) if isinstance(custom_raw, str) and custom_raw else None
    dest = _resolve_backup_dest(custom)
    dest.parent.mkdir(parents=True, exist_ok=True)

    def _do_backup() -> None:
        src_conn = sqlite3.connect(str(src))
        dst_conn = sqlite3.connect(str(dest))
        try:
            with dst_conn:
                src_conn.backup(dst_conn)
        finally:
            src_conn.close()
            dst_conn.close()

    await asyncio.to_thread(_do_backup)
    await audit.record(
        AuditEventType.BACKUP_CREATED.value,
        actor=actor,
        details={"path": str(dest)},
    )
    return BackupResultOut(path=str(dest), size_bytes=dest.stat().st_size)


@router.post(
    "/shutdown",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_token)],
)
async def shutdown_daemon() -> Response:
    _schedule_shutdown()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

"""Publish this daemon's token, port and start time from ``daemon.json``.

``coffer.infrastructure.daemon.entry`` allocates the port and mints the token
BEFORE uvicorn binds, and writes both to ``~/.coffer/daemon.json``. The app has
to read them back, because the auth dependency and ``/daemon/status`` answer out
of module-level singletons rather than out of that file.

Split out of the composition root for the file-size guideline, alongside
``credential_composition`` and ``engine_config_composition``.
"""

from __future__ import annotations

import logging
import pathlib

from coffer.infrastructure.daemon.pid_lock import read as read_daemon_json
from coffer.infrastructure.sync.identity import coffer_dir
from coffer.surfaces.http import daemon_routes
from coffer.surfaces.http.auth import set_active_token

_logger = logging.getLogger(__name__)


def daemon_json_path() -> pathlib.Path:
    return coffer_dir() / "daemon.json"


def publish_daemon_identity() -> None:
    """Read token + port + started_at if ``daemon.json`` exists.

    Absent is fine — an in-process app (tests, ``uvicorn coffer.main:app``) has
    no discovery file. Present-but-unreadable is a real fault and MUST fail
    startup: swallowing it left the token unset, so every authenticated route
    answered 503 while ``/daemon/status`` said "ready".
    """
    json_path = daemon_json_path()
    if not json_path.exists():
        return
    try:
        info = read_daemon_json(json_path)
    except (ValueError, KeyError, OSError) as exc:
        _logger.error(
            "daemon.json at %s is unreadable (%r); refusing to start without a token",
            json_path,
            exc,
        )
        raise RuntimeError(f"daemon.json at {json_path} is unreadable: {exc}") from exc
    set_active_token(info.token)
    daemon_routes.set_port(info.port)
    daemon_routes.set_started_at(info.started_at)

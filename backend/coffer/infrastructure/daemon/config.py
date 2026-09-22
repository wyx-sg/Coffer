"""``~/.coffer/daemon-config.json`` — the daemon's settings, read before it binds.

This is the one piece of Coffer configuration that cannot live in SQLite. The
port is chosen in :func:`coffer.infrastructure.daemon.bootstrap.acquire`, which
runs before the database is opened and before migrations have created any table
to read; and it cannot be an environment variable either, because the daemon is
spawned detached by whichever surface first needs one (the CLI, an agent's MCP
shim) and inherits *that caller's* environment — a shell profile reaches the
user's own terminal and nothing else. So: a small file beside ``daemon.json``,
read with nothing but the standard library.

The two files are deliberately a pair, and deliberately distinguishable:
``daemon-config.json`` is configuration, goes IN, and survives shutdown;
``daemon.json`` is runtime state, comes OUT, and is unlinked on exit.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from pathlib import Path
from typing import Any

from coffer.infrastructure.daemon.atomic_write import write_json_0600

_logger = logging.getLogger(__name__)

#: The port the daemon binds when the user has configured nothing — and the
#: single place that number is written down, so bootstrap, the CLI and every
#: message quoting it cannot drift apart.
#:
#: It is a fixed default rather than the head of a scan: a local service with a
#: web UI is bookmarked and its origin keys the browser's ``localStorage``, so a
#: port that moves silently resets the UI's own remembered state. A default the
#: daemon refuses to start without is the trade that ADR
#: "The Desktop Shell Returns" chose in its place.
DEFAULT_PORT = 8000

#: Ports the daemon will accept as a fixed port. The floor is not arbitrary:
#: binding below 1024 needs privileges the daemon does not have and must not
#: acquire, so accepting one would only trade a clear rejection now for an
#: unbindable port later.
MIN_PORT = 1024
MAX_PORT = 65535


class InvalidPort(ValueError):  # noqa: N818
    """Raised when a caller asks for a port the daemon could never bind."""


def _coffer_dir() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer"


def config_path() -> Path:
    return _coffer_dir() / "daemon-config.json"


def validate_port(port: int) -> int:
    """Return ``port`` if the daemon could bind it; raise :class:`InvalidPort`."""
    if not MIN_PORT <= port <= MAX_PORT:
        raise InvalidPort(f"port must be between {MIN_PORT} and {MAX_PORT}, got {port}")
    return port


def _read_raw() -> dict[str, Any] | None:
    """The parsed config file, or ``None`` when absent/unreadable/malformed."""
    path = config_path()
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        # A hand-mangled config must not stop the daemon from starting — that
        # would be unrecoverable from the UI, which needs a running daemon. Warn
        # loudly and fall back to the default port; `coffer daemon port show`
        # reports the same problem where the user can act on it.
        _logger.warning("daemon config at %s is unreadable (%r); ignoring it", path, exc)
        return None
    if not isinstance(payload, dict):
        _logger.warning("daemon config at %s is not an object; ignoring it", path)
        return None
    return payload


def config_is_readable() -> bool:
    """False only when the file exists but could not be parsed.

    Lets a surface distinguish "no fixed port configured" from "there is a
    config file and we could not read it", which :func:`read_fixed_port`
    deliberately collapses into the same ``None``.
    """
    return not config_path().exists() or _read_raw() is not None


def read_fixed_port() -> int | None:
    """The port the user pinned, or ``None`` to mean :data:`DEFAULT_PORT`.

    ``None`` also covers an absent, unreadable, or nonsensical file: every one
    of those means "no usable instruction", and the safe reading of no
    instruction is the default port — never a different one. Callers that want
    the number the daemon will actually bind should ask :func:`effective_port`
    rather than substituting the default themselves.
    """
    payload = _read_raw()
    if payload is None:
        return None
    port = payload.get("port")
    if port is None:
        return None
    if not isinstance(port, int) or isinstance(port, bool):
        _logger.warning("daemon config port %r is not an integer; ignoring it", port)
        return None
    try:
        return validate_port(port)
    except InvalidPort as exc:
        _logger.warning("daemon config %s; ignoring it", exc)
        return None


def effective_port() -> int:
    """The port the daemon will bind at its next start.

    One function so that "what port is Coffer on?" has one answer across the
    bind itself, the CLI's ``show``, and the pre-flight that diagnoses a
    squatted port — three places that each used to reach for the default on
    their own and could therefore disagree.
    """
    fixed = read_fixed_port()
    return DEFAULT_PORT if fixed is None else fixed


def _merge(**fields: Any) -> None:
    """Write ``fields`` into the config file, keeping everything else.

    Merging rather than replacing is what lets several settings share one file.
    Keys this build does not know are preserved for the same reason: a config
    written by a newer Coffer must survive being touched by an older one. That
    preservation is the whole forward-compatibility story — earlier builds also
    stamped a ``version``, which nothing ever read or branched on; files that
    carry it keep it, as an unknown key like any other.
    """
    payload = dict(_read_raw() or {})
    payload.update(fields)
    write_json_0600(config_path(), payload)


def write_fixed_port(port: int | None) -> None:
    """Pin the daemon's port, or clear the setting with ``None``.

    Clearing returns the daemon to :data:`DEFAULT_PORT`; it does not return it
    to picking a port for itself, which Coffer no longer does.

    Takes effect at the next daemon start — a running daemon owns its bound
    socket and cannot move without restarting.
    """
    if port is not None:
        validate_port(port)
    _merge(port=port)


# --- idle shutdown ----------------------------------------------------------


#: How long the daemon serves with nothing asking of it before standing down,
#: when the user has configured nothing.
#:
#: Twelve hours is "overnight, and then some": a working day's gap in use does
#: not cost a restart, and a machine left alone over a weekend does not keep a
#: python process and its MCP upstreams resident for two days over nothing.
#: The daemon is a login service now (``coffer daemon install-service``), so
#: without a ceiling it would otherwise live exactly as long as the login
#: session does.
DEFAULT_IDLE_SHUTDOWN_HOURS = 12.0

#: The shortest idle window the daemon will honour. Below this the setting
#: stops meaning "nobody is using it" and starts meaning "restart constantly":
#: a client that goes quiet for a minute between calls is normal, and paying a
#: five-second cold start for each gap is worse than the process it saves.
MIN_IDLE_SHUTDOWN_HOURS = 0.25


class InvalidIdleShutdown(ValueError):  # noqa: N818
    """Raised when a caller asks for an idle window the daemon will not honour."""


def validate_idle_shutdown_hours(hours: float | None) -> float | None:
    """Return ``hours`` if the daemon will honour it; raise otherwise.

    ``None`` is a legitimate setting and means "never stand down" — the daemon
    stays up for as long as the login session does. It is the setting for
    someone whose channels must answer at any hour.
    """
    if hours is None:
        return None
    if hours < MIN_IDLE_SHUTDOWN_HOURS:
        raise InvalidIdleShutdown(
            f"the idle window must be at least {MIN_IDLE_SHUTDOWN_HOURS} hours "
            f"(or unset, to never stand down), got {hours}"
        )
    return hours


def read_idle_shutdown_hours() -> float | None:
    """The configured idle window, or :data:`DEFAULT_IDLE_SHUTDOWN_HOURS`.

    Distinguishes "not configured" (absent key → the default) from "configured
    off" (``null`` → never stand down), which a bare ``get`` could not.
    """
    payload = _read_raw()
    if payload is None or "idle_shutdown_hours" not in payload:
        return DEFAULT_IDLE_SHUTDOWN_HOURS
    raw = payload["idle_shutdown_hours"]
    if raw is None:
        return None
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        _logger.warning("daemon config idle_shutdown_hours %r is not a number; ignoring it", raw)
        return DEFAULT_IDLE_SHUTDOWN_HOURS
    try:
        return validate_idle_shutdown_hours(float(raw))
    except InvalidIdleShutdown as exc:
        _logger.warning("daemon config %s; ignoring it", exc)
        return DEFAULT_IDLE_SHUTDOWN_HOURS


def write_idle_shutdown_hours(hours: float | None) -> None:
    """Set the idle window, or ``None`` to never stand down.

    Takes effect at the next daemon start: the running daemon read this when
    it booted, and a setting that re-read itself mid-run would be a second way
    for the same value to be true.
    """
    validate_idle_shutdown_hours(hours)
    _merge(idle_shutdown_hours=hours)


# --- machine identity -------------------------------------------------------
#
# A machine has two separate things (spec vault-sync "Identity is derived, the
# name is a label"), and this file holds them for opposite reasons.
#
# ``machine_name`` is a label the user may change at any time. It lives here
# because the daemon needs it before it has published anything, and because
# nothing references it — a rename costs nothing.
#
# ``machine_id`` is a key: it names this machine's descriptor and its registry
# row in the vault the machines share. It is DERIVED from the host
# (see ``infrastructure.sync.machine_id``), and what is written here is only a
# cache, so the daemon does not shell out to ``ioreg`` on every boot. The cache
# is never authoritative: deleting it recomputes the same value, and a cached
# value that disagrees with the host is the host's to win.


def default_machine_name() -> str:
    """This host's name, as a person would say it.

    ``.local`` is mDNS's suffix rather than part of what the user calls their
    laptop, so it is stripped; the hostname is used verbatim otherwise.
    """
    name = socket.gethostname().strip()
    if name.endswith(".local"):
        name = name[: -len(".local")]
    return name or "coffer"


def read_machine_name() -> str:
    """The display name for this machine, defaulting from the hostname."""
    payload = _read_raw()
    if payload is not None:
        name = payload.get("machine_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return default_machine_name()


def write_machine_name(name: str) -> None:
    """Rename this machine. Free by construction: nothing references the name.

    An empty name clears the setting rather than storing a blank, so the next
    read falls back to the hostname instead of showing the user nothing.
    """
    _merge(machine_name=name.strip() or None)


def read_cached_machine_id() -> str | None:
    """The cached derived id, or None when there is nothing usable cached."""
    payload = _read_raw()
    if payload is None:
        return None
    cached = payload.get("machine_id")
    return cached.strip() if isinstance(cached, str) and cached.strip() else None


def write_cached_machine_id(machine_id: str) -> None:
    """Cache a derived id. Only ever called with a value the host produced."""
    _merge(machine_id=machine_id)

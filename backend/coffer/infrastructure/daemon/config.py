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
from pathlib import Path
from typing import Any

from coffer.infrastructure.daemon.atomic_write import write_json_0600

_logger = logging.getLogger(__name__)

_CONFIG_VERSION = 1

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
        # loudly and fall back to automatic selection; `coffer daemon port show`
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
    """The user's fixed port, or ``None`` for automatic selection.

    ``None`` also covers an absent, unreadable, or nonsensical file: every one
    of those means "no usable instruction", and the safe reading of no
    instruction is the behaviour Coffer had before this setting existed.
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


def write_fixed_port(port: int | None) -> None:
    """Fix the daemon's port, or clear the setting with ``None``.

    Takes effect at the next daemon start — a running daemon owns its bound
    socket and cannot move without restarting.
    """
    if port is not None:
        validate_port(port)
    path = config_path()
    payload: dict[str, Any] = {"version": _CONFIG_VERSION, "port": port}
    write_json_0600(path, payload)

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


#: Keys an earlier build wrote that no current setting reads. Every read
#: ignores them and every write removes them (spec daemon "Change residency from
#: the settings page or the command line"): ``idle_shutdown_hours`` configured
#: an idle stand-down the daemon no longer has.
_RETIRED_KEYS = frozenset({"idle_shutdown_hours"})


def _merge(**fields: Any) -> None:
    """Write ``fields`` into the config file, keeping everything else.

    Merging rather than replacing is what lets several settings share one file.
    Keys this build does not know are preserved for the same reason: a config
    written by a newer Coffer must survive being touched by an older one. That
    preservation is the whole forward-compatibility story — earlier builds also
    stamped a ``version``, which nothing ever read or branched on; files that
    carry it keep it, as an unknown key like any other.

    The one exception is :data:`_RETIRED_KEYS`: a setting that no longer
    decides anything is dropped on every write, so the file stops stating it.
    """
    payload = {k: v for k, v in (_read_raw() or {}).items() if k not in _RETIRED_KEYS}
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


# --- machine identity -------------------------------------------------------
#
# A machine has two separate things (spec vault-sync "Derive machine identity from the host", the
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


# --- experimental features --------------------------------------------------
#
# A machine's own choice of which experimental features are on (spec
# experimental-features "Decide a feature's state per machine"). It lives here
# rather than in the database on purpose: the database syncs, and a switch in
# it would switch every machine at once. Unlike the settings above, a change
# takes effect at once — the running daemon's feature service holds the value
# and writes it here before it answers.

#: The environment variable that pins features for tests and CI,
#: ``vault_sync=on,memory=off``. Read once, when the daemon starts.
FEATURES_ENV = "COFFER_FEATURES"

_ON = frozenset({"on", "true", "1"})
_OFF = frozenset({"off", "false", "0"})


def read_feature_settings() -> dict[str, bool]:
    """The ``features`` object: every key whose value is a boolean.

    Keys the registry does not know are returned too — deciding which keys
    count is the feature service's job, and a key written by a newer build
    must not be read as absent by an older one. A non-boolean value is warned
    about and left out, which reads as "no setting".
    """
    payload = _read_raw()
    raw = payload.get("features") if payload is not None else None
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        _logger.warning("daemon config features %r is not an object; ignoring it", raw)
        return {}
    out: dict[str, bool] = {}
    for key, value in raw.items():
        if isinstance(value, bool):
            out[str(key)] = value
        else:
            _logger.warning("daemon config feature %s=%r is not a boolean; ignoring it", key, value)
    return out


def write_feature_setting(key: str, enabled: bool) -> None:
    """Set one feature in the ``features`` object, keeping every other key in it."""
    payload = _read_raw() or {}
    current = payload.get("features")
    features = dict(current) if isinstance(current, dict) else {}
    features[key] = enabled
    _merge(features=features)


def parse_feature_pins(raw: str | None, known: tuple[str, ...]) -> dict[str, bool]:
    """Parse ``COFFER_FEATURES`` (``key=on|off``, comma-separated).

    An unknown key, or an entry that is not ``key=on|off``, is warned about and
    skipped: a typo in a test's environment must not stop the daemon, and it
    must not pin something the registry does not have.
    """
    pins: dict[str, bool] = {}
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        key, sep, value = entry.partition("=")
        key, value = key.strip(), value.strip().lower()
        if not sep or value not in _ON | _OFF:
            _logger.warning("%s entry %r is not key=on|off; ignoring it", FEATURES_ENV, entry)
            continue
        if key not in known:
            _logger.warning("%s names unknown feature %r; ignoring it", FEATURES_ENV, key)
            continue
        pins[key] = value in _ON
    return pins


def read_feature_pins(known: tuple[str, ...]) -> dict[str, bool]:
    """The pins in this process's environment."""
    return parse_feature_pins(os.environ.get(FEATURES_ENV), known)


def read_withdrawn_memory_delivery() -> list[str]:
    """The agents a switched-off ``memory`` took the delivery hook out of.

    Kept beside the switch that caused it, and machine-local for the same
    reason: switching ``memory`` back on must put the hook back into exactly
    these agents, and nowhere else (``application.memory.delivery_switch``).
    """
    payload = _read_raw()
    raw = payload.get("memory_delivery_withdrawn") if payload is not None else None
    if not isinstance(raw, list):
        return []
    return [str(uid) for uid in raw if isinstance(uid, str) and uid]


def write_withdrawn_memory_delivery(uids: list[str]) -> None:
    """Replace the withdrawn list. An empty list is not written into a config
    that never held one."""
    payload = _read_raw()
    if not uids and (payload is None or "memory_delivery_withdrawn" not in payload):
        return
    _merge(memory_delivery_withdrawn=list(uids))

"""The ``coffer config`` key registry: the settings read before the daemon binds.

``daemon.port`` is stored in the pre-bind settings file, read and written here
with no daemon involved, because the state it most needs changing from is "the
daemon cannot start" (spec daemon "Bind a fixed, settable port"). Every other
setting is a control on the Settings page.
"""

from __future__ import annotations

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon import config as daemon_config
from coffer.surfaces.cli._config_registry import Reading, Setting, SettingValueError


def _parse_port(raw: str) -> int:
    try:
        return daemon_config.validate_port(int(raw))
    except (ValueError, daemon_config.InvalidPort):
        raise SettingValueError(
            f"daemon.port takes a port number between {daemon_config.MIN_PORT} and "
            f"{daemon_config.MAX_PORT}, got {raw!r}"
        ) from None


def _port_read() -> Reading:
    configured = daemon_config.read_fixed_port()
    value = daemon_config.DEFAULT_PORT if configured is None else configured
    lines = [str(value)]
    if not daemon_config.config_is_readable():
        lines.append(
            f"the config file at {daemon_config.config_path()} exists but could not be read; "
            f"the default port {daemon_config.DEFAULT_PORT} is in effect"
        )
    return Reading(
        value, daemon_config.DEFAULT_PORT, lines=lines, extra={"configured_port": configured}
    )


def _port_apply(port: int | None) -> list[str]:
    """Write the file whatever the daemon is doing, then say whether a restart
    is owed — only when a live daemon is on a different port."""
    daemon_config.write_fixed_port(port)
    lines = [f"daemon.port = {daemon_config.effective_port()}"]
    info = bootstrap.live_daemon()
    if info is None:
        lines.append("daemon not running — the setting applies at the next start")
    elif daemon_config.effective_port() != info.port:
        lines.append(
            f"the daemon is still on port {info.port}; "
            "the change applies at the next start — run: coffer daemon restart"
        )
    return lines


DAEMON_PORT = Setting(
    "daemon.port",
    "port",
    "The port the daemon listens on (works with no daemon running)",
    "~/.coffer/daemon-config.json",
    _parse_port,
    _port_read,
    _port_apply,
    lambda: _port_apply(None),
)


def static_settings() -> list[Setting]:
    return [DAEMON_PORT]


def lookup(key: str) -> Setting | None:
    """The key's setting, or ``None`` for a key that is not stored pre-bind."""
    return next((s for s in static_settings() if s.key == key), None)


def listing(prefix: str) -> list[Setting]:
    """Every key under ``prefix``."""
    return [s for s in static_settings() if s.key.startswith(prefix)]

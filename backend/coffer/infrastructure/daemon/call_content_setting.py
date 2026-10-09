"""Whether calls record their content, kept in ``~/.coffer/daemon-config.json``
(spec mcp-gateway "Switch call content recording per machine")."""

from __future__ import annotations

from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.atomic_write import write_json_0600

_KEY = "record_call_content"


class DaemonConfigCallContent:
    """``CallContentSettingPort`` over the daemon config's ``record_call_content``."""

    def read(self) -> bool | None:
        value = (daemon_config.read_payload() or {}).get(_KEY)
        return value if isinstance(value, bool) else None

    def write(self, enabled: bool) -> None:
        # Merged into the file, every other key kept (``config._merge``).
        payload = dict(daemon_config.read_payload() or {})
        payload[_KEY] = enabled
        write_json_0600(daemon_config.config_path(), payload)

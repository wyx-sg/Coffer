"""The feature service's settings, kept in ``~/.coffer/daemon-config.json``."""

from __future__ import annotations

from coffer.infrastructure.daemon import config as daemon_config


class DaemonConfigFeatureSettings:
    """Adapts :class:`coffer.application.features.FeatureSettingsPort` to the
    ``features`` object of the daemon config, written through its merge."""

    def read(self) -> dict[str, bool]:
        return daemon_config.read_feature_settings()

    def write(self, key: str, enabled: bool) -> None:
        daemon_config.write_feature_setting(key, enabled)

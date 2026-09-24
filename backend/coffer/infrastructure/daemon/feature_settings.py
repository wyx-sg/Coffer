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


class DaemonConfigWithdrawnDelivery:
    """Adapts ``application.memory.delivery_switch.WithdrawnDeliveryPort`` to
    the ``memory_delivery_withdrawn`` list of the daemon config."""

    def read(self) -> list[str]:
        return daemon_config.read_withdrawn_memory_delivery()

    def write(self, uids: list[str]) -> None:
        daemon_config.write_withdrawn_memory_delivery(uids)

"""Graduated and retired features, applied to ``daemon-config.json`` at startup."""

from __future__ import annotations

import logging

from coffer.domain import features as feature_registry
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.atomic_write import write_json_0600

_logger = logging.getLogger(__name__)


def apply_feature_lifecycle() -> None:
    """Migrate graduated features' configuration and clean up retired ones'.

    Reads ``GRADUATED_FEATURES`` and ``RETIRED_FEATURES`` (spec
    experimental-features "Move a graduated feature's configuration and clean
    up a retired one's"). For each graduated feature its switch is dropped from
    ``features`` and each mapped setting moves to its new top-level key; for
    each retired one its switch and named settings are removed. The file is
    rewritten atomically only when something changed, with one log line per
    key touched. Idempotent: a second run finds nothing left to do.
    """
    payload = daemon_config.read_payload()
    if payload is None:
        return
    changed = False
    raw_features = payload.get("features")
    features = dict(raw_features) if isinstance(raw_features, dict) else {}

    def drop_switch(key: str, event: str) -> None:
        nonlocal changed
        if key in features:
            del features[key]
            changed = True
            _logger.info(event, extra={"feature": key, "config_key": f"features.{key}"})

    for graduated in feature_registry.GRADUATED_FEATURES:
        drop_switch(graduated.key, "daemon.config.graduated_switch_removed")
        for old, new in graduated.moved.items():
            if old not in payload:
                continue
            value = payload.pop(old)
            kept = new in payload
            if not kept:
                payload[new] = value
            changed = True
            _logger.info(
                "daemon.config.graduated_setting_moved",
                extra={"feature": graduated.key, "from": old, "to": new, "kept_existing": kept},
            )
    for retired in feature_registry.RETIRED_FEATURES:
        drop_switch(retired.key, "daemon.config.retired_switch_removed")
        for extra_key in retired.strip:
            if extra_key in payload:
                del payload[extra_key]
                changed = True
                _logger.info(
                    "daemon.config.retired_setting_removed",
                    extra={"feature": retired.key, "config_key": extra_key},
                )
    if not changed:
        return
    if isinstance(raw_features, dict):
        payload["features"] = features
    write_json_0600(daemon_config.config_path(), payload)

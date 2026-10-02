"""A test-only experimental feature, for the tests of the feature mechanism.

The registry (``coffer.domain.features.EXPERIMENTAL_FEATURES``) names the four
experimental features, and the daemon's own wiring asks about them, so a test
registers its fake feature BESIDE them rather than in their place. The gates,
the switch, the pins and the listings are then exercised against a feature
that exists only in the test that registers it. Every lookup in
``coffer.domain.features`` reads the registry on each call, so replacing the
tuple is the whole of registering one.
"""

from __future__ import annotations

import pytest

from coffer.domain import features as domain_features
from coffer.domain.features import ExperimentalFeature
from coffer.infrastructure.daemon import config as daemon_config

#: The key the fake feature is registered under.
FAKE_FEATURE = "fake_feature"

#: The route prefix it owns unless a test names another.
FAKE_PREFIX = "/api/v1/fake-feature"


#: The registry as shipped: the four experimental features.
REAL_FEATURES = domain_features.EXPERIMENTAL_FEATURES


def enable_all_in_config() -> None:
    """Switch every shipped feature on in this test's ``daemon-config.json``.

    The suite pins all four on (``tests/conftest.py``); a test of the switch
    itself removes that pin (``monkeypatch.delenv(daemon_config.FEATURES_ENV)``)
    and starts from this, so a switch it makes is a setting rather than a
    refused write to a pinned feature.
    """
    for key in domain_features.feature_keys():
        daemon_config.write_feature_setting(key, True)


def replace_registry(
    monkeypatch: pytest.MonkeyPatch, *features: ExperimentalFeature
) -> tuple[ExperimentalFeature, ...]:
    """Replace the registry with ``features`` for the rest of the test.

    For unit tests that never boot the daemon: the app's wiring asks about the
    shipped keys, so an app-booting test uses :func:`register_fake_features`.
    """
    monkeypatch.setattr(domain_features, "EXPERIMENTAL_FEATURES", tuple(features))
    return tuple(features)


def register_fake_features(
    monkeypatch: pytest.MonkeyPatch, *features: ExperimentalFeature
) -> tuple[ExperimentalFeature, ...]:
    """Add ``features`` to the shipped registry for the rest of the test."""
    monkeypatch.setattr(domain_features, "EXPERIMENTAL_FEATURES", REAL_FEATURES + tuple(features))
    return tuple(features)


def register_fake_feature(
    monkeypatch: pytest.MonkeyPatch,
    *,
    key: str = FAKE_FEATURE,
    route_prefixes: tuple[str, ...] = (FAKE_PREFIX,),
    kinds: tuple[str, ...] = (),
) -> ExperimentalFeature:
    """Register one fake feature beside the shipped ones and return it."""
    feature = ExperimentalFeature(key=key, route_prefixes=route_prefixes, kinds=kinds)
    register_fake_features(monkeypatch, feature)
    return feature


__all__ = [
    "FAKE_FEATURE",
    "FAKE_PREFIX",
    "REAL_FEATURES",
    "enable_all_in_config",
    "register_fake_feature",
    "register_fake_features",
    "replace_registry",
]

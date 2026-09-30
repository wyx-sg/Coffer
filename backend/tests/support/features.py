"""A test-only experimental feature, for the tests of the feature mechanism.

The registry (``coffer.domain.features.EXPERIMENTAL_FEATURES``) is empty while
no capability is experimental, so the gates, the switch, the pins and the
listings are exercised against a feature that exists only in the test that
registers it. Every lookup in ``coffer.domain.features`` reads the registry on
each call, so replacing the tuple is the whole of registering one.
"""

from __future__ import annotations

import pytest

from coffer.domain import features as domain_features
from coffer.domain.features import ExperimentalFeature

#: The key the fake feature is registered under.
FAKE_FEATURE = "fake_feature"

#: The route prefix it owns unless a test names another.
FAKE_PREFIX = "/api/v1/fake-feature"


def register_fake_features(
    monkeypatch: pytest.MonkeyPatch, *features: ExperimentalFeature
) -> tuple[ExperimentalFeature, ...]:
    """Replace the registry with ``features`` for the rest of the test."""
    monkeypatch.setattr(domain_features, "EXPERIMENTAL_FEATURES", tuple(features))
    return tuple(features)


def register_fake_feature(
    monkeypatch: pytest.MonkeyPatch,
    *,
    key: str = FAKE_FEATURE,
    route_prefixes: tuple[str, ...] = (FAKE_PREFIX,),
    kinds: tuple[str, ...] = (),
) -> ExperimentalFeature:
    """Register one fake feature as the whole registry and return it."""
    feature = ExperimentalFeature(key=key, route_prefixes=route_prefixes, kinds=kinds)
    register_fake_features(monkeypatch, feature)
    return feature


__all__ = [
    "FAKE_FEATURE",
    "FAKE_PREFIX",
    "register_fake_feature",
    "register_fake_features",
]

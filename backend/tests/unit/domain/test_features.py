"""The experimental-feature registry: its keys, and the channel default."""

from __future__ import annotations

import pytest

from coffer import build_channel
from coffer.domain.features import (
    EXPERIMENTAL_FEATURES,
    ExperimentalFeature,
    FeatureDisabled,
    FeaturePinned,
    FeatureUnknown,
    channel_default,
    feature_for_kind,
    feature_for_path,
    feature_keys,
    get_feature,
    is_registered,
)
from tests.support.features import FAKE_FEATURE, register_fake_feature, register_fake_features


def test_the_registry_is_empty_while_no_capability_is_experimental() -> None:
    """Sync, knowledge and memory graduated; nothing has joined since."""
    assert EXPERIMENTAL_FEATURES == ()
    assert feature_keys() == ()
    assert feature_for_kind("knowledge") is None
    assert feature_for_path("/api/v1/sync/status") is None


def test_a_registered_feature_is_found_by_key_kind_and_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feature = register_fake_feature(
        monkeypatch, route_prefixes=("/api/v1/fake", "/api/v1/other"), kinds=("fake_kind",)
    )
    assert feature_keys() == (FAKE_FEATURE,)
    assert is_registered(FAKE_FEATURE)
    assert get_feature(FAKE_FEATURE) is feature
    assert feature_for_kind("fake_kind") == FAKE_FEATURE
    assert feature_for_kind("skill") is None
    assert feature_for_path("/api/v1/fake") == FAKE_FEATURE
    assert feature_for_path("/api/v1/other/{uid}") == FAKE_FEATURE
    # A prefix is a path segment, not a string prefix.
    assert feature_for_path("/api/v1/fakery") is None


def test_features_are_listed_in_registry_order(monkeypatch: pytest.MonkeyPatch) -> None:
    register_fake_features(
        monkeypatch,
        ExperimentalFeature(key="b_feature", route_prefixes=()),
        ExperimentalFeature(key="a_feature", route_prefixes=()),
    )
    assert feature_keys() == ("b_feature", "a_feature")


def test_an_unregistered_key_is_refused() -> None:
    assert not is_registered("workflow")
    with pytest.raises(FeatureUnknown) as exc:
        get_feature("workflow")
    assert exc.value.code == "FEATURE_UNKNOWN"
    assert exc.value.feature == "workflow"


def test_the_channel_default_is_off_on_stable_and_on_on_dev() -> None:
    assert channel_default("stable") is False
    assert channel_default("dev") is True


def test_the_repository_carries_the_dev_channel() -> None:
    """Only the release workflow stamps `stable`; a checkout is always `dev`."""
    assert build_channel.CHANNEL == "dev"


def test_the_disabled_error_names_the_command_that_switches_it_on() -> None:
    err = FeatureDisabled(FAKE_FEATURE)
    assert err.code == "FEATURE_DISABLED"
    assert err.feature == FAKE_FEATURE
    assert f"coffer config set feature.{FAKE_FEATURE} on" in str(err)


def test_the_pinned_error_names_its_key() -> None:
    err = FeaturePinned(FAKE_FEATURE)
    assert err.code == "FEATURE_PINNED"
    assert err.feature == FAKE_FEATURE

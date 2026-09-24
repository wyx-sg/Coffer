"""The experimental-feature registry: its keys, and the channel default."""

from __future__ import annotations

import pytest

from coffer import build_channel
from coffer.domain.features import (
    EXPERIMENTAL_FEATURES,
    FeatureDisabled,
    FeaturePinned,
    FeatureUnknown,
    channel_default,
    feature_keys,
    get_feature,
    is_registered,
)


def test_the_registry_holds_exactly_the_three_features_in_order() -> None:
    assert feature_keys() == ("vault_sync", "knowledge", "memory")


def test_each_feature_names_its_own_route_prefix_cli_group_and_page() -> None:
    by_key = {f.key: f for f in EXPERIMENTAL_FEATURES}
    assert by_key["vault_sync"].route_prefixes == ("/api/v1/sync",)
    assert by_key["knowledge"].cli_groups == ("knowledge",)
    assert by_key["memory"].web_routes == ("/memory",)


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
    err = FeatureDisabled("knowledge")
    assert err.code == "FEATURE_DISABLED"
    assert err.feature == "knowledge"
    assert "coffer daemon features enable knowledge" in str(err)


def test_the_pinned_error_names_its_key() -> None:
    err = FeaturePinned("memory")
    assert err.code == "FEATURE_PINNED"
    assert err.feature == "memory"

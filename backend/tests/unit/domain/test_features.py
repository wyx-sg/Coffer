"""The experimental-feature registry: its four keys, and what each owns."""

from __future__ import annotations

import pytest

from coffer.domain.features import (
    EXPERIMENTAL_FEATURES,
    ExperimentalFeature,
    FeatureDisabled,
    FeaturePinned,
    FeatureUnknown,
    feature_for_kind,
    feature_for_path,
    feature_keys,
    get_feature,
)
from tests.support.features import FAKE_FEATURE, replace_registry


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="the registry names the four experimental features",
)
def test_the_registry_names_the_four_experimental_features() -> None:
    assert feature_keys() == ("knowledge", "memory", "sync", "models")
    assert feature_for_kind("knowledge") == "knowledge"
    assert feature_for_kind("memory") == "memory"
    assert feature_for_kind("provider") == "models"
    # Everything else is always there, channels and conversations included.
    for kind in ("agent", "skill", "mcp_server", "secret", "channel"):
        assert feature_for_kind(kind) is None
    assert feature_for_path("/api/v1/chat/conversations") is None
    assert feature_for_path("/api/v1/channels/abc") is None
    assert feature_for_path("/api/v1/providers/price-list") == "models"
    assert feature_for_path("/api/v1/models/list-models") == "models"
    assert feature_for_path("/api/v1/proxy/status") == "models"
    assert feature_for_path("/api/v1/usage/summary") == "models"
    assert feature_for_path("/api/v1/knowledge/collections") == "knowledge"
    assert feature_for_path("/api/v1/memory/partitions") == "memory"
    assert feature_for_path("/api/v1/sync/status") == "sync"
    # Always-on routes, and the routes the agent pages and the internal engine use.
    for path in (
        "/api/v1/agents",
        "/api/v1/agent-providers",
        "/api/v1/internal-engine-config",
        "/api/v1/vault/status",
        "/api/v1/skills",
        "/api/v1/secrets",
    ):
        assert feature_for_path(path) is None
    assert {f.key for f in EXPERIMENTAL_FEATURES} == set(feature_keys())


def test_a_registered_feature_is_found_by_key_kind_and_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (feature,) = replace_registry(
        monkeypatch,
        ExperimentalFeature(
            key=FAKE_FEATURE,
            route_prefixes=("/api/v1/fake", "/api/v1/other"),
            kinds=("fake_kind",),
        ),
    )
    assert feature_keys() == (FAKE_FEATURE,)
    assert get_feature(FAKE_FEATURE) is feature
    assert feature_for_kind("fake_kind") == FAKE_FEATURE
    assert feature_for_kind("skill") is None
    assert feature_for_path("/api/v1/fake") == FAKE_FEATURE
    assert feature_for_path("/api/v1/other/{uid}") == FAKE_FEATURE
    # A prefix is a path segment, not a string prefix.
    assert feature_for_path("/api/v1/fakery") is None


def test_features_are_listed_in_registry_order(monkeypatch: pytest.MonkeyPatch) -> None:
    replace_registry(
        monkeypatch,
        ExperimentalFeature(key="b_feature", route_prefixes=()),
        ExperimentalFeature(key="a_feature", route_prefixes=()),
    )
    assert feature_keys() == ("b_feature", "a_feature")


def test_an_unregistered_key_is_refused() -> None:
    with pytest.raises(FeatureUnknown) as exc:
        get_feature("workflow")
    assert exc.value.code == "FEATURE_UNKNOWN"
    assert exc.value.feature == "workflow"


def test_the_disabled_error_names_the_setting_that_switches_it_on() -> None:
    err = FeatureDisabled(FAKE_FEATURE)
    assert err.code == "FEATURE_DISABLED"
    assert err.feature == FAKE_FEATURE
    assert "Settings › Features" in str(err)  # noqa: RUF001


def test_the_pinned_error_names_its_key() -> None:
    err = FeaturePinned(FAKE_FEATURE)
    assert err.code == "FEATURE_PINNED"
    assert err.feature == FAKE_FEATURE

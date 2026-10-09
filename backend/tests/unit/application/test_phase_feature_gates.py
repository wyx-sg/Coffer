"""The non-REST gates of the two experimental features, one unit each.

Spec experimental-features: a switched-off feature closes every surface, not
only its routes. The REST, kind, CLI and tool gates are exercised through the
real daemon in ``tests/integration/surfaces/http/test_phase_feature_gates.py``;
this file holds what has no route to ask — the attention sources — and the
registry itself.
"""

from __future__ import annotations

from coffer.application.channel.attention import ChannelAttentionSource
from coffer.application.sync.attention import SyncAttentionSource
from coffer.domain.features import (
    EXPERIMENTAL_FEATURES,
    KNOWLEDGE,
    MEMORY,
    feature_keys,
)

# --- channels --------------------------------------------------------------


def test_the_channel_attention_source_belongs_to_no_feature() -> None:
    """Channels are always on, so their attention source is always asked."""
    assert ChannelAttentionSource.feature is None


# --- sync ------------------------------------------------------------------


def test_the_sync_attention_source_belongs_to_no_feature() -> None:
    """Vault sync graduated, so its attention source is always asked."""
    assert SyncAttentionSource.feature is None


# --- the registry ----------------------------------------------------------


def test_every_registered_feature_owns_a_surface() -> None:
    """A feature with neither a route prefix nor a kind would close nothing."""
    for feature in EXPERIMENTAL_FEATURES:
        assert feature.route_prefixes, feature.key
    assert feature_keys() == (KNOWLEDGE, MEMORY)

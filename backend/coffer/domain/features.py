"""The experimental features, and the release channel that decides their default.

One registry, and every surface takes the list from it (spec
experimental-features "Declare the experimental features in one registry"). A
capability outside this registry is always on.

A feature leaves the registry once it is ready, and its gates are then deleted
(ADR "Experimental Features Instead of a Release Branch").

Pure: names and the surfaces each key owns, nothing that reads a file or an
environment. Where a feature's state comes from is the application layer's
question (``coffer.application.features``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from coffer.domain.error_base import CofferError

#: The release channel a build carries. ``stable`` is stamped by the release
#: workflow onto a tagged build; every other build is ``dev``.
Channel = Literal["stable", "dev"]

#: Where a feature's current state was decided, highest precedence first:
#: a ``COFFER_FEATURES`` pin, the machine's own setting, the channel default.
FeatureSource = Literal["pin", "setting", "channel"]


@dataclass(frozen=True)
class ExperimentalFeature:
    """One registered feature, and what of the daemon it owns.

    The HTTP gates key on these, so no gate spells a prefix or a kind of its
    own: ``surfaces.http.routing`` puts a router behind the feature whose
    prefix its paths sit under, and the kind-agnostic resource routes refuse a
    resource whose kind a switched-off feature owns. The CLI needs no entry
    here — its commands reach the daemon over those routes and print the
    ``FEATURE_DISABLED`` answer — and neither does the web UI, which reads each
    feature's state off the daemon status.
    """

    key: str
    #: REST path prefixes whose routes answer 404 ``FEATURE_DISABLED`` while off.
    route_prefixes: tuple[str, ...]
    #: Resource kinds the feature owns: while it is off, the kind-agnostic
    #: resource routes answer 404 ``FEATURE_DISABLED`` for them and leave their
    #: rows out of a list.
    kinds: tuple[str, ...] = ()


#: Empty: no capability is experimental right now. Sync, knowledge and memory
#: graduated at 1.0 — their entries and every gate that named them were
#: deleted, and migration 0116 stripped their stored settings. A feature joins
#: by adding one entry here; it leaves by deleting that entry, every gate that
#: names it, and its stored settings (spec experimental-features "Declare the
#: experimental features in one registry").
EXPERIMENTAL_FEATURES: tuple[ExperimentalFeature, ...] = ()


# The lookups read the registry on every call rather than from an index built
# at import: it holds a handful of entries at most, and a test registers a fake
# feature by replacing ``EXPERIMENTAL_FEATURES`` alone.


def feature_keys() -> tuple[str, ...]:
    """Every registered key, in registry order."""
    return tuple(f.key for f in EXPERIMENTAL_FEATURES)


def is_registered(key: str) -> bool:
    return key in feature_keys()


def get_feature(key: str) -> ExperimentalFeature:
    """The registered feature named ``key``; raise :class:`FeatureUnknown` otherwise."""
    for feature in EXPERIMENTAL_FEATURES:
        if feature.key == key:
            return feature
    raise FeatureUnknown(key)


def feature_for_kind(kind: str) -> str | None:
    """The feature that owns resource kind ``kind``, or ``None`` for a kind
    that is always there."""
    for feature in EXPERIMENTAL_FEATURES:
        if kind in feature.kinds:
            return feature.key
    return None


def feature_for_path(path: str) -> str | None:
    """The feature whose route prefixes ``path`` sits under, or ``None``."""
    for feature in EXPERIMENTAL_FEATURES:
        for prefix in feature.route_prefixes:
            if path == prefix or path.startswith(prefix + "/"):
                return feature.key
    return None


def channel_default(channel: Channel) -> bool:
    """A feature's state when nothing pins it and the machine has no setting."""
    return channel == "dev"


class FeatureUnknown(CofferError):  # noqa: N818
    """A key the registry does not declare."""

    code = "FEATURE_UNKNOWN"

    def __init__(self, key: str) -> None:
        super().__init__(f"{key!r} is not an experimental feature")
        self.feature = key


class FeaturePinned(CofferError):  # noqa: N818
    """A write to a feature ``COFFER_FEATURES`` pins for this daemon's lifetime."""

    code = "FEATURE_PINNED"

    def __init__(self, key: str) -> None:
        super().__init__(f"{key} is pinned by COFFER_FEATURES and cannot be switched")
        self.feature = key


class FeatureDisabled(CofferError):  # noqa: N818
    """A request that reached a surface of a switched-off feature."""

    code = "FEATURE_DISABLED"

    def __init__(self, key: str) -> None:
        super().__init__(
            f"{key} is switched off on this machine — run: coffer config set feature.{key} on"
        )
        self.feature = key

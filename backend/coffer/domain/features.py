"""The experimental features.

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

#: Where a feature's current state was decided, highest precedence first:
#: a ``COFFER_FEATURES`` pin, the machine's own setting, the built-in default
#: (off).
FeatureSource = Literal["pin", "setting", "default"]


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


#: The four experimental features (spec experimental-features "Declare the
#: experimental features in one registry"). Everything else — the shell, the
#: overview, Agents, the MCP gateway and its custom tools, Skills, Secrets,
#: Activity, Settings, Conversations and Channels — is always on and owns no
#: entry.
#:
#: ``knowledge`` — the knowledge collections. ``memory`` — agent memory.
#: ``sync`` — vault sync. ``models`` — Model providers, the local model proxy
#: and the Usage tab. Every one is off until the person switches it on, on this
#: machine. A feature joins by adding one entry here and tagging its other
#: surfaces with its key; it leaves by deleting that entry and every gate that
#: names it (and, once released, a migration that strips its stored setting).
KNOWLEDGE = "knowledge"
MEMORY = "memory"
SYNC = "sync"
MODELS = "models"

EXPERIMENTAL_FEATURES: tuple[ExperimentalFeature, ...] = (
    ExperimentalFeature(
        key=KNOWLEDGE,
        route_prefixes=("/api/v1/knowledge",),
        kinds=("knowledge",),
    ),
    ExperimentalFeature(
        key=MEMORY,
        route_prefixes=("/api/v1/memory",),
        kinds=("memory",),
    ),
    ExperimentalFeature(
        key=SYNC,
        route_prefixes=("/api/v1/sync",),
    ),
    ExperimentalFeature(
        key=MODELS,
        route_prefixes=(
            "/api/v1/providers",
            "/api/v1/models",
            "/api/v1/proxy",
            "/api/v1/usage",
        ),
        kinds=("provider",),
    ),
)


# The lookups read the registry on every call rather than from an index built
# at import: it holds a handful of entries at most, and a test registers a fake
# feature by replacing ``EXPERIMENTAL_FEATURES`` alone.


def feature_keys() -> tuple[str, ...]:
    """Every registered key, in registry order."""
    return tuple(f.key for f in EXPERIMENTAL_FEATURES)


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

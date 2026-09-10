"""Deterministic, kind-agnostic projection of a resource to/from a bundle doc.

A *resource document* is the plain-dict form written to
``resources/<kind>/<name>.yaml`` in an export bundle. Determinism is
load-bearing (spec vault-export-import "Determinism"): machine-local, churn-prone fields
(``id``, ``created_at``, ``updated_at``) are excluded and the encoder
(infrastructure) dumps with sorted keys — so two exports of an unchanged vault
produce byte-identical files, and the user can diff a bundle to see exactly
what they are carrying.

This module is pure: it deals in dicts only. YAML encoding lives in
infrastructure.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from coffer.domain.sync.errors import SyncSerializationError

#: Fields that are part of the document, in canonical order.
_DOC_FIELDS = ("kind", "name", "description", "enabled", "config", "scope")


@dataclass(frozen=True)
class ResourceDoc:
    """The exported projection of a resource: identity + curation + config."""

    kind: str
    name: str
    description: str | None
    enabled: bool
    config: dict[str, Any]
    # Activation scope (ADR per-agent-resource-scope). An ordinary field with no dedicated
    # machinery (spec vault-export-import "Scope"): it names agents, never paths, so it is
    # exempt from ${HOME} normalization and rides the document unmodified.
    scope: Any = None


def resource_to_doc(
    *,
    kind: str,
    name: str,
    description: str | None,
    enabled: bool,
    config: Mapping[str, Any],
    scope: Any,
) -> dict[str, Any]:
    """Project a resource into its canonical bundle-document dict.

    ``id``/``created_at``/``updated_at`` are intentionally absent — they are
    machine-local and would make two exports of the same vault differ.
    ``scope`` is always emitted (even ``None``) so files stay byte-identical
    across exports, matching ``description``'s always-present-may-be-null style.
    """
    return {
        "kind": kind,
        "name": name,
        "description": description,
        "enabled": enabled,
        "config": dict(config),
        "scope": scope,
    }


def parse_resource_doc(data: Mapping[str, Any]) -> ResourceDoc:
    """Validate and parse a bundle document back into a ``ResourceDoc``."""
    missing = [f for f in ("kind", "name", "enabled", "config") if f not in data]
    if missing:
        raise SyncSerializationError(f"document missing field(s): {', '.join(missing)}")
    kind = data["kind"]
    name = data["name"]
    description = data.get("description")
    enabled = data["enabled"]
    config = data["config"]
    scope = data.get("scope")
    if not isinstance(kind, str) or not kind:
        raise SyncSerializationError("'kind' must be a non-empty string")
    if not isinstance(name, str) or not name:
        raise SyncSerializationError("'name' must be a non-empty string")
    if description is not None and not isinstance(description, str):
        raise SyncSerializationError("'description' must be a string or null")
    if not isinstance(enabled, bool):
        raise SyncSerializationError("'enabled' must be a boolean")
    if not isinstance(config, Mapping):
        raise SyncSerializationError("'config' must be a mapping")
    extra = [k for k in data if k not in _DOC_FIELDS]
    if extra:
        raise SyncSerializationError(f"unexpected field(s): {', '.join(sorted(extra))}")
    return ResourceDoc(
        kind=kind,
        name=name,
        description=description,
        enabled=enabled,
        config=dict(config),
        scope=scope,
    )

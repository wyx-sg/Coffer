"""Deterministic, kind-agnostic projection of a resource to/from a sync document.

A *sync document* is the plain-dict form written to
``resources/<kind>/<name>.yaml`` in the sync workspace. Determinism is
load-bearing: machine-local, churn-prone fields (``id``, ``created_at``,
``updated_at``) are excluded, and the encoder (infrastructure) dumps with
sorted keys — so two machines that hold the same logical resource produce
byte-identical files and git reports no spurious conflict.

This module is pure: it deals in dicts only. YAML encoding lives in
infrastructure.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from coffer.domain.sync.errors import SyncSerializationError

#: Fields that are part of the document, in canonical order.
_DOC_FIELDS = ("kind", "name", "description", "enabled", "config")


@dataclass(frozen=True)
class ResourceDoc:
    """The synced projection of a resource: identity + curation + config only."""

    kind: str
    name: str
    description: str | None
    enabled: bool
    config: dict[str, Any]


def resource_to_doc(
    *,
    kind: str,
    name: str,
    description: str | None,
    enabled: bool,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Project a resource into its canonical sync-document dict.

    ``id``/``created_at``/``updated_at`` are intentionally absent — they are
    machine-local and would churn the diff on every machine.
    """
    return {
        "kind": kind,
        "name": name,
        "description": description,
        "enabled": enabled,
        "config": dict(config),
    }


def parse_resource_doc(data: Mapping[str, Any]) -> ResourceDoc:
    """Validate and parse a sync document back into a ``ResourceDoc``."""
    missing = [f for f in ("kind", "name", "enabled", "config") if f not in data]
    if missing:
        raise SyncSerializationError(f"document missing field(s): {', '.join(missing)}")
    kind = data["kind"]
    name = data["name"]
    description = data.get("description")
    enabled = data["enabled"]
    config = data["config"]
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
    )

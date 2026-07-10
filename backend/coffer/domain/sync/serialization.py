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
_DOC_FIELDS = ("kind", "name", "description", "enabled", "config", "scope")


@dataclass(frozen=True)
class ResourceDoc:
    """The synced projection of a resource: identity + curation + config only."""

    kind: str
    name: str
    description: str | None
    enabled: bool
    config: dict[str, Any]
    # Framework-level machine x agent activation scope (ADR-045). Rides the
    # doc verbatim — it holds machine ULIDs / agent names, never paths, so it
    # is exempt from ${HOME} normalization and per-machine override stripping.
    scope: dict[str, Any] | None
    # Whether the "scope" key was present in the source document at all.
    # v4+ writers always emit it (see resource_to_doc), so this is True for
    # every doc this process writes. A pre-v4 peer's doc lacks the key
    # entirely — that is a DIFFERENT thing from an explicit `scope: null`
    # (an active opinion that the resource is unscoped/dormant): the v3 doc
    # simply has no opinion on scope at all. Importer reconciliation must
    # treat "absent" as "leave local scope alone" and "explicit null" as "set
    # it to None" — conflating the two would let an old peer's doc silently
    # flip a locally-scoped channel to active-everywhere on import,
    # reintroducing the double-adapter race ADR-043 exists to prevent.
    scope_present: bool = True


def resource_to_doc(
    *,
    kind: str,
    name: str,
    description: str | None,
    enabled: bool,
    config: Mapping[str, Any],
    scope: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Project a resource into its canonical sync-document dict.

    ``id``/``created_at``/``updated_at`` are intentionally absent — they are
    machine-local and would churn the diff on every machine. ``scope`` is
    always emitted (even ``None``) so files stay byte-deterministic, matching
    ``description``'s always-present-may-be-null style.
    """
    return {
        "kind": kind,
        "name": name,
        "description": description,
        "enabled": enabled,
        "config": dict(config),
        "scope": dict(scope) if scope is not None else None,
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
    # Absent key (a v3 workspace doc, pre-Task-6) tolerates to None — never a
    # hard failure, so old-schema docs still import cleanly. `scope_present`
    # distinguishes that "no opinion" case from an explicit `scope: null`
    # (see ResourceDoc.scope_present docstring above) — the importer relies
    # on this to decide whether to touch local scope at all.
    scope_present = "scope" in data
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
    if scope is not None and not isinstance(scope, Mapping):
        raise SyncSerializationError("'scope' must be a mapping or null")
    extra = [k for k in data if k not in _DOC_FIELDS]
    if extra:
        raise SyncSerializationError(f"unexpected field(s): {', '.join(sorted(extra))}")
    return ResourceDoc(
        kind=kind,
        name=name,
        description=description,
        enabled=enabled,
        config=dict(config),
        scope=dict(scope) if scope is not None else None,
        scope_present=scope_present,
    )

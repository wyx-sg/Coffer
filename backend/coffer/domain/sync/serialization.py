"""Deterministic, kind-agnostic projection of a resource to/from a synced doc.

A *resource document* is the plain-dict form written to
``resources/<kind>/<uid>.yaml`` in the tree the vault converges through, and
it is identity plus description plus config — nothing else. The path is keyed
on the **uid** and the name lives inside the document, which is what makes a
rename a modification of one file rather than a deletion beside an addition
(ADR resource-identity-is-an-immutable-uid). Determinism is
load-bearing (spec vault-sync "Serialize deterministically"): machine-local, churn-prone
fields (``id``, ``created_at``, ``updated_at``) are excluded and the encoder
(infrastructure) dumps with sorted keys — so an unchanged vault serializes to
byte-identical files on every machine and on every round, and the user can
read the remote's history with their own git tools.

**A resource's reach is not part of the document.** ``enabled`` and ``scope``
read like two fields but they are one thing: the resource's *reach*, set by one
control in the UI — whether this resource is live, and for which agents. Reach
is machine-local (spec vault-sync "Keep reach machine-local"). It is set on the
machine it applies to and each machine sets its own, so publishing it would let
one machine silently re-answer a question another machine had already answered
locally: the laptop that deliberately left a server dark would find it live
again after the desktop's next round, with nothing in the history that reads
like a decision anyone made. What travels is the resource — its identity and
its configuration. What it reaches, here, stays here.

Every kind gets a document, including ``channel``, which was once withheld
entirely: a channel names inside its own config the single machine whose daemon
runs its adapter, so the document can travel without the adapter travelling
with it. This module stays kind-agnostic and projects whatever it is handed.

This module is pure: it deals in dicts only. YAML encoding lives in
infrastructure.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from coffer.domain.sync.errors import SyncSerializationError

#: Fields that are part of the document, in canonical order. ``uid`` leads
#: because it is the identity — everything after it is something the identity
#: has, including the name.
_DOC_FIELDS = ("uid", "kind", "name", "description", "config")

# NOTE — there is no ignored-field list here any more, and the layout version
# is why. It used to name ``enabled`` and ``scope``, the reach fields older
# builds wrote into the document, and read-and-drop them rather than refusing
# them: a shared tree still receiving documents from an un-upgraded machine
# would otherwise have quarantined them on every machine that *had* upgraded,
# and one stale machine would have stalled convergence for all of them.
#
# Bumping the bundle layout to 2 (``manifest.SCHEMA_VERSION``) retires that
# argument outright, because an un-upgraded machine no longer writes into this
# tree at all — it reads the manifest, finds a layout it does not know, and
# refuses the remote before it imports or exports anything. The only documents
# that can arrive here now are ones a build with this layout wrote, and such a
# build never emits a reach field. So an unexpected key is once again what it
# reads like: a typo'd document that would import as something other than what
# it says, and it is refused.


@dataclass(frozen=True)
class ResourceDoc:
    """The exported projection of a resource: identity + description + config."""

    uid: str
    kind: str
    name: str
    description: str | None
    config: dict[str, Any] = field(default_factory=dict)


def resource_to_doc(
    *,
    uid: str,
    kind: str,
    name: str,
    description: str | None,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Project a resource into its canonical bundle-document dict.

    ``uid`` is emitted even though the document's own path is named after it,
    because the path is the tree's filing and the document is what the vault
    reads: a machine applying a removal has only the path, and a machine
    applying an upsert reads the document, and both have to reach the same
    identity. Writing it twice is also what lets the user (or a merge) see the
    identity in a diff of the file alone.

    ``id``/``created_at``/``updated_at`` are intentionally absent — they are
    machine-local and would make two exports of the same vault differ.
    ``uid`` is emphatically not one of them: it is minted once and never
    changes, so it is identical on every machine that holds this resource.

    ``enabled`` and ``scope`` are absent for a stronger reason than churn: they
    are one thing, the resource's reach, and reach is machine-local. It is set
    on the machine it applies to, and each machine sets its own; emitting it
    here would let this machine's answer overwrite an answer another machine
    had already given itself, which is not something the user can see happening
    from either end.

    ``description`` is always emitted, even as ``None``, so files stay
    byte-identical across exports rather than gaining and losing a key.
    """
    return {
        "uid": uid,
        "kind": kind,
        "name": name,
        "description": description,
        "config": dict(config),
    }


def parse_resource_doc(data: Mapping[str, Any]) -> ResourceDoc:
    """Validate and parse a bundle document back into a ``ResourceDoc``."""
    missing = [f for f in ("uid", "kind", "name", "config") if f not in data]
    if missing:
        raise SyncSerializationError(f"document missing field(s): {', '.join(missing)}")
    uid = data["uid"]
    kind = data["kind"]
    name = data["name"]
    description = data.get("description")
    config = data["config"]
    if not isinstance(uid, str) or not uid:
        raise SyncSerializationError("'uid' must be a non-empty string")
    if not isinstance(kind, str) or not kind:
        raise SyncSerializationError("'kind' must be a non-empty string")
    if not isinstance(name, str) or not name:
        raise SyncSerializationError("'name' must be a non-empty string")
    if description is not None and not isinstance(description, str):
        raise SyncSerializationError("'description' must be a string or null")
    if not isinstance(config, Mapping):
        raise SyncSerializationError("'config' must be a mapping")
    # Strict about every field nobody has ever written: a typo'd key is a
    # document that would import as something other than what it says.
    extra = [k for k in data if k not in _DOC_FIELDS]
    if extra:
        raise SyncSerializationError(f"unexpected field(s): {', '.join(sorted(extra))}")
    return ResourceDoc(
        uid=uid,
        kind=kind,
        name=name,
        description=description,
        config=dict(config),
    )

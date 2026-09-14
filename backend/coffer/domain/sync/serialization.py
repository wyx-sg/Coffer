"""Deterministic, kind-agnostic projection of a resource to/from a bundle doc.

A *resource document* is the plain-dict form written to
``resources/<kind>/<name>.yaml`` in an export bundle, and it is identity plus
description plus config — nothing else. Determinism is load-bearing (spec
vault-sync "Determinism"): machine-local, churn-prone fields (``id``,
``created_at``, ``updated_at``) are excluded and the encoder (infrastructure)
dumps with sorted keys — so two exports of an unchanged vault produce
byte-identical files, and the user can diff a bundle to see exactly what they
are carrying.

**A resource's reach is not part of the document.** ``enabled`` and ``scope``
read like two fields but they are one thing: the resource's *reach*, set by one
control in the UI — whether this resource is live, and for which agents. Reach
is machine-local (spec vault-sync ``## What does not sync``). It is set on the
machine it applies to and each machine sets its own, so publishing it would let
one machine silently re-answer a question another machine had already answered
locally: the laptop that deliberately left a server dark would find it live
again after the desktop's next round, with nothing in the history that reads
like a decision anyone made. What travels is the resource — its identity and
its configuration. What it reaches, here, stays here.

Which resources get a document *at all* is not decided here. A kind that is
bound to one machine never reaches this module —
:data:`coffer.application.sync.exporter.MACHINE_LOCAL_KINDS` is the one place
that names them — so this stays kind-agnostic and projects whatever it is
handed.

This module is pure: it deals in dicts only. YAML encoding lives in
infrastructure.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from coffer.domain.sync.errors import SyncSerializationError

#: Fields that are part of the document, in canonical order.
_DOC_FIELDS = ("kind", "name", "description", "config")

#: Fields this build reads and then throws away — the reach fields older builds
#: wrote into the document.
#:
#: Ignoring them is the point, not an oversight left behind. The shared tree
#: already holds documents written before reach stopped travelling, and it will
#: keep receiving freshly written ones from every machine in the remote that
#: has not upgraded yet. Refusing them the way an unknown field is refused
#: would quarantine those documents on every machine that *has* upgraded, so
#: one stale machine would stall convergence for all of them. They are named
#: here, read, and dropped.
#:
#: The applier reaches the same outcome by a different route — it reads the
#: keys it wants straight off the YAML and never calls this parser — so this
#: leniency is what :meth:`BundlePort.read_resource_docs` gives a caller that
#: wants the whole document, not the gate the import path passes through.
_IGNORED_FIELDS = ("enabled", "scope")


@dataclass(frozen=True)
class ResourceDoc:
    """The exported projection of a resource: identity + description + config."""

    kind: str
    name: str
    description: str | None
    config: dict[str, Any] = field(default_factory=dict)


def resource_to_doc(
    *,
    kind: str,
    name: str,
    description: str | None,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Project a resource into its canonical bundle-document dict.

    ``id``/``created_at``/``updated_at`` are intentionally absent — they are
    machine-local and would make two exports of the same vault differ.

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
        "kind": kind,
        "name": name,
        "description": description,
        "config": dict(config),
    }


def parse_resource_doc(data: Mapping[str, Any]) -> ResourceDoc:
    """Validate and parse a bundle document back into a ``ResourceDoc``."""
    missing = [f for f in ("kind", "name", "config") if f not in data]
    if missing:
        raise SyncSerializationError(f"document missing field(s): {', '.join(missing)}")
    kind = data["kind"]
    name = data["name"]
    description = data.get("description")
    config = data["config"]
    if not isinstance(kind, str) or not kind:
        raise SyncSerializationError("'kind' must be a non-empty string")
    if not isinstance(name, str) or not name:
        raise SyncSerializationError("'name' must be a non-empty string")
    if description is not None and not isinstance(description, str):
        raise SyncSerializationError("'description' must be a string or null")
    if not isinstance(config, Mapping):
        raise SyncSerializationError("'config' must be a mapping")
    # Strict about fields nobody has ever written — a typo'd key is a document
    # that would import as something other than what it says — but deliberately
    # lenient about the two reach fields, which are read and discarded.
    extra = [k for k in data if k not in _DOC_FIELDS and k not in _IGNORED_FIELDS]
    if extra:
        raise SyncSerializationError(f"unexpected field(s): {', '.join(sorted(extra))}")
    return ResourceDoc(
        kind=kind,
        name=name,
        description=description,
        config=dict(config),
    )

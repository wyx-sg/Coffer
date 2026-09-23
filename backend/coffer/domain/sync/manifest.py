"""The bundle manifest (spec vault-sync).

``manifest.json`` sits at the root of the working tree the vault converges
through. It carries the tree's layout schema version, and that version is the
only load-bearing field: a build that does not know a newer layout refuses the
remote (``SYNC_BUNDLE_TOO_NEW``) rather than applying a partially-understood
tree — or publishing into one, which is the worse half, because an exporter
converges the areas it knows about and would publish a newer build's documents
as deletions the user never made.

:func:`refuse_if_too_new` is where that refusal is enforced, and every path
that reads the remote's documents into this vault calls it first: the converge
round, the rebuild, and the restore. It is the sync-layer twin of
``DB_SCHEMA_TOO_NEW``, which stops an older build from opening a newer
database (``infrastructure.persistence.migrations_runner``), and it matters
more here than there — a shared remote means the mistake reaches the user's
other machines.

Because it is the only thing an older build can read, the manifest's own shape
is frozen forever: the file keeps this name, stays JSON, and keeps
``schema_version`` as a plain integer. A layout change bumps the number; it
never moves or re-formats the number itself, or the build that most needs to
read it is the one that cannot.

``created_at`` is written only when a caller supplies one, and a converge
export never does. It is a machine-local fact, and the working tree an export
writes is the thing git three-way-merges: a timestamp restamped every round
would make every round stage a change (so an unchanged vault would commit), and
would make two machines meeting for the first time conflict on this file before
they had disagreed about anything real. Determinism — the same vault serializing
to the same bytes on every machine — is normative (spec vault-sync
"Serialize deterministically"), and a per-export timestamp is exactly
the "machine-local field" that rule says to strip.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from coffer.domain.sync.errors import SyncBundleTooNew, SyncSerializationError

#: Where the manifest lives, relative to the working tree's root. One constant
#: rather than a literal per reader: the writer and the version gate must name
#: the same path, or the gate silently guards nothing.
MANIFEST_PATH = "manifest.json"

#: Bundle layout version, bumped only on an incompatible layout change.
#: 1 = the layout introduced by the vault-sync ADR (manifest + mirrored trees +
#: resources/ + state/ + machines/ + optional credentials/). The continuous-sync
#: workspace layouts that preceded it are a different artifact entirely and
#: are not readable here.
#: 2 = resource and state documents are filed under a resource's immutable
#: ``uid`` rather than its name (ADR resource-identity-is-an-immutable-uid), so
#: a rename modifies one file instead of publishing a deletion beside an
#: addition. This is exactly the kind of change the gate below exists for: a
#: build on layout 1 reading a layout-2 tree would see every document's path
#: change at once and apply the lot as "the user deleted everything and created
#: everything" — the ``ResourceService.delete`` cascade, the orphaned-credential
#: release, the whole loss this layout was introduced to stop. Refusing the
#: remote outright is the only safe reading such a build has.
SCHEMA_VERSION = 2


@dataclass(frozen=True)
class Manifest:
    schema_version: int = SCHEMA_VERSION
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        doc: dict[str, object] = {"schema_version": self.schema_version}
        if self.created_at is not None:
            doc["created_at"] = self.created_at.isoformat()
        return doc

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Manifest:
        try:
            version = int(data["schema_version"])  # type: ignore[call-overload]
        except (KeyError, TypeError, ValueError) as e:
            raise SyncSerializationError(f"manifest missing/invalid schema_version: {e}") from e
        raw_created = data.get("created_at")
        created: datetime | None = None
        if raw_created is not None:
            try:
                created = datetime.fromisoformat(str(raw_created))
            except ValueError as e:
                raise SyncSerializationError(f"manifest has an invalid created_at: {e}") from e
        return cls(schema_version=version, created_at=created)


def refuse_if_too_new(raw: bytes | None) -> None:
    """Raise ``SyncBundleTooNew`` when ``raw`` declares a layout newer than
    this build's.

    ``raw`` is ``manifest.json`` exactly as the remote holds it, or ``None``
    when the remote has no manifest at all. The caller hands over bytes rather
    than a parsed document because the whole point is to read a file this build
    may not fully understand — and it reads it through :meth:`Manifest.from_dict`
    rather than picking the field out itself, so there is one answer in the
    codebase to "what does this manifest say".

    **A manifest it cannot read is not a refusal.** Absent, not JSON, not a
    mapping, or a ``schema_version`` that is not a number — none of those can be
    produced by a newer Coffer, which writes this file the way the contract
    above freezes it. They are a virgin remote, a hand-edit, or corruption, and
    refusing them would wedge sync on a file the user cannot discover from the
    error. Only a version this build can read *and* does not support stops a
    round; anything else proceeds, which is what every build has done until now.
    """
    if raw is None:
        return
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return
    if not isinstance(doc, Mapping):
        return
    try:
        manifest = Manifest.from_dict(doc)
    except SyncSerializationError:
        return
    if manifest.schema_version > SCHEMA_VERSION:
        raise SyncBundleTooNew(manifest.schema_version, SCHEMA_VERSION)

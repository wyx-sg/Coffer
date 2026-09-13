"""The export bundle manifest (spec vault-sync).

``manifest.json`` carries the bundle's layout schema version. The version is
the only load-bearing field: a build that does not know a newer layout refuses
the bundle (``SYNC_BUNDLE_TOO_NEW``) instead of applying a partially-understood
snapshot.

``created_at`` is written only when a caller supplies one, and a converge
export never does. It is a machine-local fact, and the working tree an export
writes is the thing git three-way-merges: a timestamp restamped every round
would make every round stage a change (so an unchanged vault would commit), and
would make two machines meeting for the first time conflict on this file before
they had disagreed about anything real. Determinism — the same vault serializing
to the same bytes on every machine — is normative (spec vault-sync
``## Determinism and path portability``), and a per-export timestamp is exactly
the "machine-local field" that rule says to strip.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from coffer.domain.sync.errors import SyncSerializationError

#: Bundle layout version, bumped only on an incompatible layout change.
#: 1 = the export/import bundle introduced by the vault-sync ADR
#: (manifest + mirrored
#: trees + resources/ + state/ + optional credentials/). The continuous-sync
#: workspace layouts that preceded it are a different artifact entirely and
#: are not readable here.
SCHEMA_VERSION = 1


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

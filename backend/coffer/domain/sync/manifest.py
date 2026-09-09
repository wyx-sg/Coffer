"""The export bundle manifest (spec 010).

``manifest.json`` carries the bundle's layout schema version plus the moment
it was written. The version is the only load-bearing field: a build that does
not know a newer layout refuses the bundle (``SYNC_BUNDLE_TOO_NEW``) instead
of applying a partially-understood snapshot. ``created_at`` is informational —
it is the one field that legitimately differs between two exports of an
otherwise unchanged vault.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from coffer.domain.sync.errors import SyncSerializationError

#: Bundle layout version, bumped only on an incompatible layout change.
#: 1 = the export/import bundle introduced by ADR-016 (manifest + mirrored
#: trees + resources/ + state/ + optional credentials/). The continuous-sync
#: workspace layouts that preceded it are a different artifact entirely and
#: are not readable here.
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Manifest:
    schema_version: int = SCHEMA_VERSION
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        created = self.created_at or datetime.now(tz=UTC)
        return {"schema_version": self.schema_version, "created_at": created.isoformat()}

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

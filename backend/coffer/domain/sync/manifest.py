"""The sync workspace manifest (spec 010).

``manifest.json`` records who produced the workspace commit and the layout
schema version, so a machine running an older build refuses to import a newer
layout (``SYNC_WORKSPACE_TOO_NEW``) rather than corrupting state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from coffer.domain.sync.errors import SyncSerializationError

#: Bumped only on an incompatible workspace-layout change.
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    machine_id: str
    coffer_version: str
    kinds: tuple[str, ...]

    @classmethod
    def create(cls, *, machine_id: str, coffer_version: str, kinds: Sequence[str]) -> Manifest:
        return cls(
            schema_version=SCHEMA_VERSION,
            machine_id=machine_id,
            coffer_version=coffer_version,
            kinds=tuple(kinds),
        )

    def to_dict(self) -> dict[str, object]:
        # Sorted, plain types — deterministic so the manifest only churns the
        # diff when something meaningful changed.
        return {
            "coffer_version": self.coffer_version,
            "kinds": sorted(self.kinds),
            "machine_id": self.machine_id,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Manifest:
        try:
            schema_version = int(data["schema_version"])  # type: ignore[call-overload]
            machine_id = str(data["machine_id"])
            coffer_version = str(data["coffer_version"])
            raw_kinds = data["kinds"]
        except (KeyError, TypeError, ValueError) as e:
            raise SyncSerializationError(f"manifest missing/invalid field: {e}") from e
        if not isinstance(raw_kinds, Sequence) or isinstance(raw_kinds, str | bytes):
            raise SyncSerializationError("manifest 'kinds' must be a list")
        return cls(
            schema_version=schema_version,
            machine_id=machine_id,
            coffer_version=coffer_version,
            kinds=tuple(str(k) for k in raw_kinds),
        )

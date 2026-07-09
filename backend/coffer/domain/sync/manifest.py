"""The sync workspace manifest (spec 010).

``manifest.json`` records only the workspace layout schema version, so it is
byte-identical on every machine and never becomes a merge conflict. A machine
running an older build refuses to import a newer layout
(``SYNC_WORKSPACE_TOO_NEW``) rather than corrupting state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from coffer.domain.sync.errors import SyncSerializationError

#: Bumped only on an incompatible workspace-layout change. 2 = tombstone-driven
#: deletion. The too-new gate is enforced from version 2 onward — a v1 build
#: predates the gate entirely, so a mixed v1/v2 fleet is unprotected and must
#: upgrade together.
SCHEMA_VERSION = 2


@dataclass(frozen=True)
class Manifest:
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Manifest:
        try:
            return cls(schema_version=int(data["schema_version"]))  # type: ignore[call-overload]
        except (KeyError, TypeError, ValueError) as e:
            raise SyncSerializationError(f"manifest missing/invalid schema_version: {e}") from e

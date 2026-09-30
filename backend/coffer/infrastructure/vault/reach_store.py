"""Where each resource reaches, on this machine only (ADR
reach-is-a-machine-local-predicate-over-a-context; spec vault-storage "Store
state in five classes by nature").

Reach is a fact about this machine — which of its agents a skill is delivered
to, whether this machine serves an MCP server at all — so it is never in a
resource's file and never committed. It is one JSON object in
``local/reach.json``::

    {"<uid>": {"enabled": true, "agents": ["<agent uid>", ...] | null, "projects": null}}

``agents: null`` is unrestricted. ``projects`` is reserved for the context's
next axis and always written ``null``. A resource with **no record** reaches
as registration would have made it: enabled, with its kind's starting scope
(``Kind.default_scope``, unrestricted for every kind that supplies none) —
which is what a resource that arrived from another machine, or a file a person
wrote by hand, gets until someone narrows it here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coffer.domain.scope import Scope
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.json_store import JsonStore


@dataclass(frozen=True)
class Reach:
    """One resource's reach on this machine."""

    enabled: bool = True
    scope: Scope | None = None

    def to_json(self) -> dict[str, Any]:
        agents = self.scope.agents if self.scope is not None else None
        return {"enabled": self.enabled, "agents": agents, "projects": None}

    @classmethod
    def from_json(cls, raw: Any) -> Reach | None:
        """A record as stored; ``None`` for one that is not an object (read
        as "no record", so the resource falls back to its defaults)."""
        if not isinstance(raw, dict):
            return None
        agents = raw.get("agents")
        scope = (
            Scope(agents=[a for a in agents if isinstance(a, str) and a])
            if isinstance(agents, list)
            else None
        )
        return cls(enabled=raw.get("enabled", True) is not False, scope=scope)

    def fingerprint(self) -> str:
        """A stable text of this reach, for the revision counter."""
        agents = self.scope.agents if self.scope is not None else None
        return f"{self.enabled}|{','.join(agents) if agents is not None else '*'}"


def reach_path(home: Path | None = None) -> Path:
    return local_root(home) / "reach.json"


class ReachStore:
    """``local/reach.json``, read whole and changed under its lock."""

    def __init__(self, path: Path | Callable[[], Path] = reach_path) -> None:
        self._store = JsonStore(path)

    def all(self) -> dict[str, Reach]:
        out: dict[str, Reach] = {}
        for uid, raw in self._store.read().items():
            reach = Reach.from_json(raw)
            if reach is not None:
                out[uid] = reach
        return out

    def get(self, uid: str) -> Reach | None:
        return Reach.from_json(self._store.read().get(uid))

    def put(self, uid: str, reach: Reach) -> None:
        def change(doc: dict[str, Any]) -> None:
            doc[uid] = reach.to_json()

        self._store.update(change)

    def remove(self, uid: str) -> None:
        def change(doc: dict[str, Any]) -> None:
            doc.pop(uid, None)

        self._store.update(change)


__all__ = ["Reach", "ReachStore", "reach_path"]

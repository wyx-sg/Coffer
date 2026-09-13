"""The developer's memory decisions, as shared vault state (spec vault-sync).

The memory layer is almost entirely derived: everything under
``~/.coffer/memory/`` is aggregated from the agents installed on **this**
machine and may be deleted and rebuilt at any time. None of it syncs. Carrying
it across would replicate one machine's agents' facts onto a machine whose
agents never produced them, where the next aggregation pass would recompute
them away — churn that buys nothing.

The overrides are the exception, for the same reason they are kept out of the
derived tree in the first place: a hide, a pin, a hand-picked supersession or a
settled conflict is a **decision**, not a computation, and it is keyed by a
fact key built to survive recomputation (spec memory FR-022, FR-040). A
decision about a fact is worth the same on both machines; the fact's derived
representation is not.

One document per override, so two machines deciding about two different facts
never touch the same path and git merges them without help.
"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from coffer.application.memory.overrides import Override

#: Kebab-case directory name under ``state/`` in the working tree.
AREA = "memory-overrides"


class OverrideRepoPort(Protocol):
    async def all(self) -> dict[str, Override]: ...
    async def set(self, override: Override, *, actor: str) -> None: ...
    async def clear(self, fact_key: str) -> None: ...


class MemoryOverrideSyncState:
    """Implements ``application.sync.ports.SyncedStatePort`` structurally."""

    def __init__(self, overrides: OverrideRepoPort) -> None:
        self._overrides = overrides

    @property
    def area(self) -> str:
        return AREA

    async def export_docs(self) -> tuple[list[tuple[str, dict[str, Any]]], list[str]]:
        """One deterministic document per decided fact.

        The fact key is the document's path, which is what keeps the documents
        disjoint: two machines deciding about two different facts stage two
        different files, and git has nothing to reconcile. The key is opaque
        and may contain characters a path cannot, so it is the *payload* that
        carries it and the filename is a stable digest of it.
        """
        docs: list[tuple[str, dict[str, Any]]] = []
        for fact_key, override in sorted((await self._overrides.all()).items()):
            docs.append(
                (
                    _doc_name(fact_key),
                    {
                        "fact_key": fact_key,
                        "hidden": override.hidden,
                        "pinned": override.pinned,
                        "superseded_by": override.superseded_by or "",
                        "conflict_choice": override.conflict_choice or "",
                    },
                )
            )
        return docs, [AREA]

    async def import_docs(self, docs: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, str]]:
        failures: list[tuple[str, str]] = []
        for rel, doc in docs:
            fact_key = doc.get("fact_key")
            if not isinstance(fact_key, str) or not fact_key:
                failures.append((rel, "no fact_key in the document"))
                continue
            await self._overrides.set(
                Override(
                    fact_key=fact_key,
                    hidden=bool(doc.get("hidden")),
                    pinned=bool(doc.get("pinned")),
                    superseded_by=str(doc.get("superseded_by") or ""),
                    conflict_choice=str(doc.get("conflict_choice") or ""),
                ),
                actor="sync",
            )
        return failures

    async def delete_docs(self, rels: list[str]) -> None:
        """Clear an override another machine took back.

        Clearing needs the fact key, and a deleted document no longer carries
        it — so the lookup goes the other way: every key whose digest matches a
        removed document is cleared. Reversing the digest is not possible and
        should not be.
        """
        removed = set(rels)
        for fact_key in list((await self._overrides.all()).keys()):
            if _doc_name(fact_key) in removed:
                await self._overrides.clear(fact_key)


def _doc_name(fact_key: str) -> str:
    """A filesystem-safe, stable name for one fact key.

    A digest rather than the key itself: a fact key is built from an agent, a
    native file and an anchor within it, so it can hold slashes, spaces and
    anything else the source did — none of which belongs in a path. The digest
    is stable, which is all the working tree needs.
    """
    return hashlib.sha256(fact_key.encode("utf-8")).hexdigest()[:32]

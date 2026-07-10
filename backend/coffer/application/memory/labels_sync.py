"""Memory store labels as a synced state area (spec 010 x spec 007 FR-017c).

A per-project memory store is named ``project-<ULID>`` — portable across
machines by construction (#287) but unreadable. The user-set display label
lived in the machine-local ``memory_store_labels`` table, so a store arriving
via sync showed as "unnamed store" on every other machine. Labels are pure
display intent and travel fine: one doc per store under
``state/memory-labels/<store>.yaml``.

Semantics are ADDITIVE: setting or renaming a label propagates (the owner
re-exports its doc); clearing a label stays machine-local — a cleared store
would otherwise resurrect from the other machine's doc anyway, and the user's
actual need is names appearing, not names vanishing.
"""

from __future__ import annotations

from typing import Protocol

AREA = "memory-labels"


class _LabelRepo(Protocol):
    async def list_all(self) -> dict[str, str]: ...
    async def get(self, store_name: str) -> str | None: ...
    async def set(self, store_name: str, label: str) -> None: ...


class MemoryLabelsSyncState:
    """Implements ``application.sync.ports.SyncedStatePort`` structurally."""

    area = AREA

    def __init__(self, labels: _LabelRepo) -> None:
        self._labels = labels

    async def export_docs(self) -> tuple[list[tuple[str, dict[str, object]]], list[str]]:
        labels = await self._labels.list_all()
        docs: list[tuple[str, dict[str, object]]] = [
            (store, {"label": label}) for store, label in sorted(labels.items())
        ]
        # Own exactly the stores labelled HERE: renames propagate as doc
        # updates; foreign labels are never dropped by this machine's export.
        return docs, sorted(labels)

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[tuple[str, str]]:
        errors: list[tuple[str, str]] = []
        for path, doc in docs:
            label = doc.get("label")
            if not isinstance(label, str) or not label.strip():
                continue  # malformed doc: skip, the owner re-exports it
            try:
                if await self._labels.get(path) != label:
                    await self._labels.set(path, label)
            except Exception as e:
                errors.append((path, str(e)))
        return errors

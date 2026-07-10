"""Memory store labels as a synced state area (spec 010 x spec 007 FR-017c).

A per-project memory store is named ``project-<ULID>`` — portable across
machines by construction (#287) but unreadable. The user-set display label
lived in the machine-local ``memory_store_labels`` table, so a store arriving
via sync showed as "unnamed store" on every other machine. Labels are pure
display intent and travel fine: one doc per store under
``state/memory-labels/<store>.yaml``.

Set, rename, and CLEAR all propagate: a clear persists as an empty-string
marker row (``StoreLabelRepo.clear``) and travels as ``{label: ""}`` — without
the marker, the cleared label would resurrect from the workspace's stale doc
within one run (review #292 finding 1). The repo's read surfaces hide the
marker, so display paths simply see "no label".
"""

from __future__ import annotations

from typing import Protocol

AREA = "memory-labels"


class _LabelRepo(Protocol):
    async def list_all(self) -> dict[str, str]: ...
    async def get(self, store_name: str) -> str | None: ...
    async def set(self, store_name: str, label: str) -> None: ...
    async def clear(self, store_name: str) -> None: ...


class MemoryLabelsSyncState:
    """Implements ``application.sync.ports.SyncedStatePort`` structurally."""

    area = AREA

    def __init__(self, labels: _LabelRepo) -> None:
        self._labels = labels

    async def export_docs(self) -> tuple[list[tuple[str, dict[str, object]]], list[str]]:
        # list_all() includes empty-string CLEAR markers, so a clear travels
        # as `{label: ""}` instead of leaving a stale doc to resurrect from.
        labels = await self._labels.list_all()
        docs: list[tuple[str, dict[str, object]]] = [
            (store, {"label": label}) for store, label in sorted(labels.items())
        ]
        # Own every store this machine holds a row for (labelled or cleared):
        # renames and clears propagate; unknown foreign labels are never
        # dropped by this machine's export.
        return docs, sorted(labels)

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[tuple[str, str]]:
        errors: list[tuple[str, str]] = []
        for path, doc in docs:
            label = doc.get("label")
            if not isinstance(label, str):
                continue  # malformed doc: skip, the owner re-exports it
            try:
                if not label.strip():
                    # A propagated clear: record the marker locally too, so
                    # this machine keeps publishing the clear, not the label.
                    if await self._labels.get(path) is not None:
                        await self._labels.clear(path)
                elif await self._labels.get(path) != label:
                    await self._labels.set(path, label)
            except Exception as e:
                errors.append((path, str(e)))
        return errors

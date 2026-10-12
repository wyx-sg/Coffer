"""Linking a folder the person keeps themselves as a collection.

A linked folder (ADR linked-knowledge-folders-are-read-only-and-machine-local)
is shared with every agent and read by Coffer, never written: nothing is
copied into the vault, and the folder's own tools keep it. Its row names the
folder and is filed machine-local (``kind.py``), because the path is true of
this disk only, so sync never carries it.
"""

from __future__ import annotations

import asyncio

from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.config import linked_folder
from coffer.domain.knowledge.entry import CollectionEntry
from coffer.domain.knowledge.errors import CollectionExists
from coffer.infrastructure.knowledge import linked, paths


async def link_folder(
    knowledge: KnowledgeService, folder: str, *, name: str | None, actor: str
) -> CollectionEntry:
    """Share ``folder`` with every agent (spec knowledge "Link a folder the
    person keeps themselves"). The name defaults to the folder's own and is a
    label, not a directory; a folder already linked is refused under the name
    it was linked as."""
    path = await asyncio.to_thread(linked.check_folder, folder)
    label = (name or path.name).strip()
    paths.check_segment(label, label)
    if label in await knowledge.collection_names() or paths.collection_dir(label).exists():
        raise CollectionExists(label)
    for row in await knowledge.linked_rows():
        if linked_folder(row.config) == str(path):
            raise CollectionExists(row.name)
    row = await knowledge.register_row(label, actor=actor, config={"folder": str(path)})
    await knowledge.catalogue_changed()
    return await asyncio.to_thread(linked.collection_entry, row.uid, row.name, str(path))


__all__ = ["link_folder"]

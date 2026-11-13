"""Writing an upload as a source (spec knowledge "Keep every upload as a
Markdown source").

An upload lands under the collection's uploads folder (``sources/`` unless its
README names another) the moment it arrives, with the frontmatter Coffer
writes on its own files and every extra key the entrance set. An upload with
pictures or attachments lands in its own ``folder`` there, beside the files it
links, named after the folder so its slug stays as unique as the folder's.
Two uploads of the same title are two sources: the second takes a free name.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from coffer.domain.knowledge.entry import ACTOR_AGENT, KnowledgeFile
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.fs import write_file


def write_source(
    collection: str,
    *,
    title: str,
    description: str,
    body: str,
    actor: str = ACTOR_AGENT,
    extra: Mapping[str, Any] | None = None,
    folder: str | None = None,
) -> KnowledgeFile:
    """Write one upload as a source; returns the file as it now reads."""
    directory = paths.uploads_dir(collection)
    if folder:
        directory = directory / folder
    directory.mkdir(parents=True, exist_ok=True)
    relative = paths.relative_of(directory)
    return write_file(
        directory=relative,
        title=title,
        description=description,
        body=body,
        actor=actor,
        relpath=f"{relative}/{folder}.md" if folder else None,
        extra=dict(extra or {}),
    )


__all__ = ["write_source"]

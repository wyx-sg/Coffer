"""The ``knowledge`` kind's config schema.

A collection Coffer keeps carries no settings. Retrieval has no modes to
choose, nothing is chunked, nothing is embedded, and no source is tracked — so
the fields the two former configs held are gone rather than carried across as
dead weight (see the knowledge data model).

The one field is for the other sort of collection: a **linked folder** (ADR
linked-knowledge-folders-are-read-only-and-machine-local). ``folder`` is the
absolute path of a folder the person keeps themselves, an Obsidian vault say,
which Coffer only shares with the agents. A row that names one is filed in the
machine-local class, because the path is true of this disk only.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
)


class KnowledgeConfig(BaseModel):
    """Empty for a collection Coffer keeps; ``folder`` for a linked one.
    Unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    folder: str | None = None

    @field_validator("folder")
    @classmethod
    def _absolute(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not os.path.isabs(value):
            raise ValueError("a linked folder is an absolute path")
        return os.path.normpath(value)

    @model_serializer(mode="wrap")
    def _drop_unset(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # A collection Coffer keeps stays ``{}`` on disk, as it always was.
        return {k: v for k, v in handler(self).items() if v is not None}


def linked_folder(config: dict[str, object]) -> str | None:
    """The folder a row links, ``None`` for a collection Coffer keeps."""
    folder = config.get("folder")
    return folder if isinstance(folder, str) and folder else None

"""The ``knowledge`` kind's config schema.

A collection carries no settings. Retrieval has no modes to choose, nothing is
chunked, nothing is embedded, and no source is tracked — so the fields the two
former configs held are gone rather than carried across as dead weight (spec
knowledge FR-081). The model stays because the Resource framework requires
every kind to name one, and an empty model is the honest description of a
collection: a directory with a name.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class KnowledgeConfig(BaseModel):
    """No configurable fields; unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")

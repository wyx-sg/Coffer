"""Wire models for ``/api/v1/memory/*``.

Mirrors ``surfaces/http/knowledge/schemas.py``: every model here describes
what a client is promised, kept deliberately separate from the domain values
(``domain.memory.fact.Fact``, ``infrastructure.memory.files``) they mirror so
trimming a domain field never silently changes the wire contract.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PartitionOut(BaseModel):
    name: str
    project_root: str
    fact_count: int


class PartitionListOut(BaseModel):
    partitions: list[PartitionOut]


class OriginOut(BaseModel):
    agent: str
    native_path: str
    anchor: str
    captured_at: str
    source_written_at: str


class FactSummaryOut(BaseModel):
    key: str
    slug: str
    partition: str
    title: str
    description: str
    type: str
    status: str
    superseded_by: str
    #: Keys of facts organise flagged this one as disagreeing with (FR-033).
    #: Nothing settles a conflict any more, so this is the model's finding and
    #: only ever that.
    conflicts_with: list[str]


class FactListOut(BaseModel):
    facts: list[FactSummaryOut]


class FactOut(FactSummaryOut):
    body: str
    origins: list[OriginOut]


class AggregationResultOut(BaseModel):
    partitions: list[str]
    facts_written: int
    sources_read: int
    sources_skipped: int
    #: Paths of native sources that failed to parse (FR-005) — left standing
    #: so a future sync keeps retrying them.
    failures: list[str]


class OrganiseResultOut(BaseModel):
    partition: str
    merged: int
    superseded: int
    conflicts: int
    model_used: bool


class ComposedContextOut(BaseModel):
    text: str
    partition: str
    facts_included: int
    facts_omitted: int
    layers: list[str]


class FileNodeOut(BaseModel):
    """One entry in a partition's own directory (FR-062).

    Same shape as the skill kind's file tree so the two surfaces render
    through one component on the frontend. ``path`` is POSIX and relative to
    the partition directory (``""`` for the root); ``abs_path`` and
    ``folder_abs_path`` are what the viewer's open-in-editor and
    reveal-in-file-manager actions need, since a browser cannot resolve a path
    on the user's own disk but the loopback daemon can.
    """

    name: str
    path: str
    abs_path: str
    folder_abs_path: str
    type: str
    size: int | None = None
    #: True on a directory whose descendants were clipped at the walk bound.
    truncated: bool = False
    children: list[FileNodeOut] = Field(default_factory=list)


class FileTreeOut(BaseModel):
    root: FileNodeOut


class FileContentOut(BaseModel):
    """One file's content, read-only.

    No fingerprint, unlike the skill kind's equivalent: a fingerprint exists
    to make a later write conditional, and this family has no write. The tree
    under ``~/.coffer/memory/`` is derived (FR-023) — an edit here would be
    overwritten by the next aggregation pass, so the surface does not offer
    one.
    """

    path: str
    abs_path: str
    folder_abs_path: str
    #: Empty when ``binary`` is true.
    content: str
    truncated: bool
    binary: bool
    size: int


class DeliveryStatusOut(BaseModel):
    agent: str
    installed: bool
    command: str
    event: str


class DeliveryStatusListOut(BaseModel):
    delivery: list[DeliveryStatusOut]


class ContextQuery(BaseModel):
    """Body for composing a session-start context (FR-050, FR-051).

    A GET-with-body would be unusual for this surface's own conventions
    (knowledge's ``search`` is a POST for the same reason: the query is
    structured, not a couple of scalar filters), so ``compose_context`` is a
    POST despite being a read — nothing here has a side effect on the memory
    tree itself.
    """

    cwd: str = Field(default="")
    agent: str | None = None
    budget_tokens: int | None = None
    #: Whether serving this payload counts as a real delivery (FR-055).
    #: The installed hook always sets this; a management-surface preview
    #: should not, so it never records a fire that did not happen.
    record_fired: bool = False

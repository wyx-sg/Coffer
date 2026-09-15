"""Wire models for ``/api/v1/memory/*``.

Mirrors ``surfaces/http/knowledge/schemas.py``: every model here describes
what a client is promised, kept deliberately separate from the domain values
(``domain.memory.fact.Fact``, ``application.memory.overrides.Override``) they
mirror so trimming a domain field never silently changes the wire contract.
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
    conflicts_with: list[str]
    proposed: bool
    #: Whether the developer's own decision hides/pins this fact (FR-040) —
    #: not reflected in the derived ``Fact`` itself, so the surface stamps it
    #: on from the current overrides table before answering.
    hidden: bool
    pinned: bool


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


class OverrideOut(BaseModel):
    fact_key: str
    hidden: bool
    pinned: bool
    superseded_by: str
    conflict_choice: str


class OverrideListOut(BaseModel):
    overrides: list[OverrideOut]


class OverridePatch(BaseModel):
    """A partial update to one fact's override (FR-040).

    Every field defaults to "leave unchanged" — only fields explicitly given
    are applied, so setting ``pinned`` never disturbs an existing ``hidden``
    decision on the same fact.
    """

    hidden: bool | None = None
    pinned: bool | None = None
    superseded_by: str | None = None
    conflict_choice: str | None = None


#: The four override fields a client may clear one at a time (FR-040).
OVERRIDE_FIELDS = ("hidden", "pinned", "superseded_by", "conflict_choice")


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

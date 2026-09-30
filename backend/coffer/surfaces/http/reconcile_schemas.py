"""Wire models for ``/api/v1/reconcile/*`` and ``/api/v1/attention``.

Hand-written against ``openspec/specs/resource-framework/contracts/api.openapi.yaml``.
No model here carries a secret value: an item's ``before`` / ``after`` is the
target's own safe rendering of the entry (an MCP entry's command and
arguments, a hook command, the keys a provider projection owns with any value
named like a key, token or secret redacted).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from coffer.application.attention import (
    AttentionItem,
    AttentionReport,
    attention_key,
    ignorable,
)
from coffer.domain.reconcile import ItemResult, Outcome, PassReport
from coffer.surfaces.http.handoff_schemas import HandoffOut, handoff_out


class ReconcileSubjectOut(BaseModel):
    kind: str
    uid: str | None
    title: str


class ReconcileItemOut(BaseModel):
    """One difference between what Coffer wants and what is there."""

    id: str = Field(description="`<target>:<key>`; what `POST /reconcile/apply` takes.")
    target: str
    key: str
    op: Literal["add", "modify", "remove"]
    disposition: Literal["repair", "report", "blocked"]
    reason_code: str
    reason: str
    subject: ReconcileSubjectOut
    file: str | None
    before: str | None = Field(description="What is there now, rendered safely; null if absent.")
    after: str | None = Field(description="What Coffer would write; null for a removal.")
    changed_params: list[str]
    outcome: Literal["planned", "applied", "failed"]
    error: str | None = None
    since: datetime | None = Field(
        default=None, description="When a writing pass first saw this difference."
    )


class ReconcileTargetOut(BaseModel):
    name: str
    kinds: list[str]
    error: str | None = Field(default=None, description="Set when the target raised.")


class ReconcilePassOut(BaseModel):
    trigger: str
    dry_run: bool
    started_at: datetime
    finished_at: datetime
    applied: int
    failed: int
    open: int


class ReconcilePlanOut(BaseModel):
    """A dry-run plan: computed on request, nothing written."""

    trigger: str
    generated_at: datetime
    period_seconds: float
    targets: list[ReconcileTargetOut]
    items: list[ReconcileItemOut]
    last_pass: ReconcilePassOut | None


class ReconcileApplyIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)


class ReconcileApplyOut(BaseModel):
    started_at: datetime
    finished_at: datetime
    items: list[ReconcileItemOut]
    failures: list[ReconcileTargetOut]


class AttentionActionOut(BaseModel):
    verb: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    body: dict[str, Any] | None = None


class AttentionItemOut(BaseModel):
    key: str = Field(
        description="`<kind>:<uid>:<reason_code>`; what `PUT /attention/ignored/{key}` takes."
    )
    #: Only an informational item can be ignored; a broken thing stays listed.
    ignorable: bool
    kind: str
    uid: str | None
    title: str
    reason_code: str
    reason: str
    severity: Literal["error", "warning", "info"]
    since: datetime | None
    action: AttentionActionOut
    #: The chore handed to an agent, when the item is one: the same prompt the
    #: kind's own page offers. ``null`` when the action alone is the fix.
    handoff: HandoffOut | None = None


class AttentionSourceErrorOut(BaseModel):
    source: str
    error: str


class AttentionOut(BaseModel):
    #: What needs a person, ignored items left out.
    items: list[AttentionItemOut]
    errors: list[AttentionSourceErrorOut]
    #: ``items`` per kind — the sidebar's badges; ignored items do not count.
    counts_by_kind: dict[str, int]
    #: The items ignored on this machine, still true but not asking.
    ignored: list[AttentionItemOut] = Field(default_factory=list)


# --- conversions ------------------------------------------------------------


def item_out(result: ItemResult, since: datetime | None) -> ReconcileItemOut:
    change = result.change
    d = change.difference
    subject = d.subject
    return ReconcileItemOut(
        id=d.id,
        target=d.target,
        key=d.key,
        op=d.op.value,
        disposition=change.decision.disposition.value,
        reason_code=change.decision.reason_code,
        reason=change.decision.reason,
        subject=ReconcileSubjectOut(kind=subject.kind, uid=subject.uid, title=subject.title),
        file=d.file,
        before=d.observed.text if d.observed else None,
        after=d.desired.text if d.desired else None,
        changed_params=list(d.changed_params),
        outcome=result.outcome.value,
        error=result.error,
        since=since,
    )


def pass_out(report: PassReport | None) -> ReconcilePassOut | None:
    if report is None:
        return None
    return ReconcilePassOut(
        trigger=report.trigger.value,
        dry_run=report.dry_run,
        started_at=report.started_at,
        finished_at=report.finished_at,
        applied=report.count(Outcome.APPLIED),
        failed=report.count(Outcome.FAILED),
        open=report.count(Outcome.PLANNED),
    )


def attention_item_out(item: AttentionItem) -> AttentionItemOut:
    a = item.action
    return AttentionItemOut(
        key=attention_key(item),
        ignorable=ignorable(item),
        kind=item.kind,
        uid=item.uid,
        title=item.title,
        reason_code=item.reason_code,
        reason=item.reason,
        severity=item.severity.value,
        since=item.since,
        action=AttentionActionOut(verb=a.verb, method=a.method, path=a.path, body=a.body),  # type: ignore[arg-type]
        handoff=handoff_out(item.handoff),
    )


def attention_out(report: AttentionReport) -> AttentionOut:
    return AttentionOut(
        items=[attention_item_out(i) for i in report.items],
        errors=[AttentionSourceErrorOut(source=e.source, error=e.error) for e in report.errors],
        counts_by_kind=dict(report.counts_by_kind),
        ignored=[attention_item_out(i) for i in report.ignored],
    )

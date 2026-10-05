"""Domain and view shapes onto the /api/v1/sync wire models."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, cast

from coffer.application.sync.views import MachineView, StoppedFile, StoppedRound, SyncStatus
from coffer.domain.plaintext_shape import MaskedValue
from coffer.domain.sync.handoffs import is_secret_file
from coffer.domain.sync.joins import JoinPreview
from coffer.domain.sync.plaintext import PlaintextContext, PlaintextFinding
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import AppliedChange, RoundRecord
from coffer.surfaces.http.handoff_schemas import handoff_out
from coffer.surfaces.http.sync_schemas import (
    AgentInventoryOut,
    AreaCountsOut,
    MachineOut,
    PlaintextFindingOut,
    ProblemOut,
    PulledCommitOut,
    RoundOut,
    SyncChangeOut,
    SyncPluginOut,
    SyncRemoteOut,
    SyncStatusOut,
    WaitingCommitOut,
)
from coffer.surfaces.http.sync_stop_schemas import (
    AreaCountOut,
    BreachOut,
    ConflictFileOut,
    HoldGroupOut,
    HoldOut,
    JoinPreviewOut,
    MaskedLineOut,
    MaskedValueOut,
    PlaintextContextOut,
    StoppedRoundOut,
    ValueShapeOut,
)

_Change = Literal["added", "modified", "removed"]


def change_out(c: AppliedChange) -> SyncChangeOut:
    status = c.status if c.status in ("added", "modified", "removed") else "modified"
    return SyncChangeOut(path=c.path, status=cast(_Change, status))


def round_out(r: RoundRecord) -> RoundOut:
    return RoundOut(
        id=r.id,
        status=r.status,
        started_at=r.started_at,
        finished_at=r.finished_at,
        trigger=r.trigger,
        from_commit=r.from_commit,
        to_commit=r.to_commit,
        snapshot=r.snapshot,
        pulled=[
            PulledCommitOut(version=c.version, time=c.time, machine=c.machine, files=c.files)
            for c in r.pulled
        ],
        applied=[change_out(c) for c in r.applied],
        pushed=[change_out(c) for c in r.pushed],
        with_machines=list(r.with_machines),
        conflicts=r.conflicts,
        held=r.held,
        stopped_on=list(r.stopped_on),
        held_direction=r.held_direction,  # type: ignore[arg-type]
        detail=r.detail,
        path=r.path,
        join=r.join,
        pulled_files=r.pulled_files,
        pushed_files=r.pushed_files,
        plaintext=plaintext_out(r.plaintext),
        folded=r.folded,
    )


def _masked_value_out(v: MaskedValue) -> MaskedValueOut:
    s = v.shape
    return MaskedValueOut(
        start=v.start,
        end=v.end,
        key=v.key,
        rule=v.rule,
        shape=ValueShapeOut(
            length=s.length,
            classes=cast(Any, list(s.classes)),
            prefix=s.prefix,
            hint=cast(Any, s.hint),
            word=s.word,
        ),
    )


def plaintext_context_out(c: PlaintextContext) -> PlaintextContextOut:
    return PlaintextContextOut(
        path=c.finding.path,
        line=c.finding.line,
        key=c.finding.key,
        rule=c.finding.rule,
        change=cast(Any, c.change),
        on_remote=c.on_remote,
        lines=[
            MaskedLineOut(
                number=row.number, text=row.text, values=[_masked_value_out(v) for v in row.values]
            )
            for row in c.lines
        ],
        diff=c.diff,
        added=c.added,
        removed=c.removed,
    )


def plaintext_out(found: Sequence[PlaintextFinding]) -> list[PlaintextFindingOut]:
    return [
        PlaintextFindingOut(path=f.path, line=f.line, key=f.key, rule=f.rule, current=f.current)
        for f in found
    ]


def remote_out(remote: SyncRemote) -> SyncRemoteOut:
    return SyncRemoteOut(
        url=remote.url,
        branch=remote.branch,
        secret_ref=remote.secret_ref,
        include_secret=remote.include_secret,
        interval_seconds=remote.interval_seconds,
        enabled=remote.enabled,
    )


def status_out(s: SyncStatus) -> SyncStatusOut:
    problem = s.problem
    return SyncStatusOut(
        configured=s.remote is not None,
        remote=remote_out(s.remote) if s.remote else None,
        machine_id=s.machine_id,
        machine_name=s.machine_name,
        joined=s.joined,
        running_since=s.running_since,
        last_round=round_out(s.last_round) if s.last_round else None,
        next_round_at=s.next_round_at,
        machines=s.machines,
        areas=AreaCountsOut(**vars(s.areas)),
        waiting=[
            WaitingCommitOut(
                version=w.version,
                time=w.time,
                writer=w.writer,
                summary=w.summary,
                changes=[change_out(c) for c in w.changes],
            )
            for w in s.waiting
        ],
        vault_path=s.vault_path,
        synchroniser=s.synchroniser,
        problem=ProblemOut(
            kind=cast(Any, problem.kind),
            message=problem.message,
            secret_ref=problem.secret_ref,
            since=problem.since,
            handoff=handoff_out(problem.handoff),
            plaintext=plaintext_out(problem.plaintext),
        )
        if problem
        else None,
        conflicts=s.conflicts,
        held=s.held,
        join_choices=s.join_choices,
        ahead=s.ahead,
        behind=s.behind,
        vault_real_path=s.vault_real_path,
        default_vault_path=s.default_vault_path,
    )


def conflict_out(f: StoppedFile) -> ConflictFileOut:
    c = f.file
    return ConflictFileOut(
        path=c.path,
        area=c.area,
        reason=c.reason,
        ours_time=c.ours_time,
        theirs_time=c.theirs_time,
        theirs_machine=c.theirs_machine,
        other_path=c.other_path,
        answer=c.answer,
        editor_path=f.editor_path,
        secret=is_secret_file(c.path),
        agent_mergeable=f.agent_mergeable,
        agent_state=cast(Any, f.agent_state),
        agent_handed_at=c.handed_at,
        agent_name=c.handed_agent,
        agent_conversation_id=c.handed_conversation,
        agent_merged_at=f.merged_at,
    )


def stopped_out(s: StoppedRound) -> StoppedRoundOut:
    stop = s.stop
    hold = stop.hold
    return StoppedRoundOut(
        kind=stop.kind.value,
        raised_at=stop.raised_at,
        local=stop.local,
        remote=stop.remote,
        join=stop.join,
        files=[conflict_out(f) for f in s.files],
        unanswered=len(stop.unanswered),
        hold=HoldOut(
            direction=hold.direction.value,
            breaches=[BreachOut(area=b.area, lost=b.lost, total=b.total) for b in hold.breaches],
            paths=list(hold.paths),
            groups=[
                HoldGroupOut(folder=g.folder, paths=list(g.paths), total=g.total) for g in s.groups
            ],
            machines=list(s.machines),
            confirmed=s.confirmed,
        )
        if hold
        else None,
    )


def preview_out(p: JoinPreview) -> JoinPreviewOut:
    return JoinPreviewOut(
        kind=p.kind.value,
        remote_tip=p.remote_tip,
        pushed_by=p.pushed_by,
        pushed_at=p.pushed_at,
        pulled=[AreaCountOut(area=a.area, files=a.files) for a in p.pulled],
        same=p.same,
        differ=list(p.differ),
        pushed=[AreaCountOut(area=a.area, files=a.files) for a in p.pushed],
        deleted=list(p.deleted),
        deleted_total=p.deleted_total,
        conflicts=list(p.conflicts),
        same_name=list(p.same_name),
        refused=p.refused,
        pulled_files=p.pulled_files,
        pushed_files=p.pushed_files,
    )


def machine_out(v: MachineView) -> MachineOut:
    d = v.descriptor
    return MachineOut(
        machine_id=d.machine_id,
        name=d.name,
        os=d.os,
        hostname=d.hostname,
        coffer_version=d.coffer_version,
        last_round_at=d.last_round_at,
        last_converged_commit=d.last_converged_commit,
        key_fingerprint=d.key_fingerprint,
        key_matches=v.key_matches,
        is_self=v.is_self,
        last_round=v.last_round,
        agents=[
            AgentInventoryOut(
                type=a.type,
                name=a.name,
                plugins=[
                    SyncPluginOut(
                        id=p.id,
                        name=p.name,
                        marketplace=p.marketplace,
                        enabled=p.enabled,
                        version=p.version,
                    )
                    for p in a.plugins
                ],
            )
            for a in d.agents
        ],
    )


__all__ = [
    "change_out",
    "conflict_out",
    "machine_out",
    "preview_out",
    "remote_out",
    "round_out",
    "status_out",
    "stopped_out",
]
